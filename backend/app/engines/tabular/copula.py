"""
Gaussian Copula Synthesizer — the heart of "not random" tabular generation.

How it works:
  1. For each column, remember its shape (quantiles for numbers, frequencies for categories)
  2. Convert every column into "normal scores", measure correlations between columns
  3. To generate: draw correlated normals, convert back through each column's shape
  4. Result: synthetic data that preserves BOTH individual distributions AND correlations

DP-Lite: pass dp={col: (epsilon, low, high)} and marginals are learned from
Laplace-noised counts (ε-DP on marginals only — we say so in the UI).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

EPOCH = pd.Timestamp("1970-01-01")
Q = np.linspace(0, 1, 1001)          # 1000-quantile grid
MODELED = ("int", "num", "date", "datetime", "cat", "money", "bool")


def _to_numeric(s: pd.Series, kind: str) -> np.ndarray:
    """Convert any column to float64 for copula modeling."""
    if kind in ("date", "datetime"):
        return (pd.to_datetime(s, errors="coerce") - EPOCH).dt.total_seconds().to_numpy(dtype=np.float64)
    if kind == "bool":
        return s.map({"true": 1, "false": 0, "True": 1, "False": 0,
                       "1": 1, "0": 0, True: 1, False: 0,
                       "yes": 1, "no": 0, "Yes": 1, "No": 0}).to_numpy(dtype=np.float64)
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype=np.float64)


def _make_psd(C: np.ndarray) -> np.ndarray:
    """Force a correlation matrix to be positive semi-definite via eigenvalue clipping."""
    C = np.nan_to_num(C, nan=0.0, posinf=1.0, neginf=-1.0)
    np.fill_diagonal(C, 1.0)
    w, v = np.linalg.eigh(C)
    w = np.clip(w, 1e-6, None)
    C_fixed = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(C_fixed))
    d[d == 0] = 1.0
    return C_fixed / np.outer(d, d)


class GaussianCopulaSynth:
    """Gaussian Copula synthesizer with DP-Lite support.

    Fits marginal distributions + a correlation matrix on training data,
    then samples new data that preserves both individual distributions
    and cross-column dependencies.
    """

    def __init__(self):
        self.cols: list[str] = []
        self.kinds: dict[str, str] = {}
        self.null_rate: dict[str, float] = {}
        self.marginals: dict[str, dict] = {}
        self.corr: np.ndarray = np.zeros((0, 0))
        self._fitted = False

    def fit(self, df: pd.DataFrame, kinds: dict[str, str],
            seed: int = 0, dp: dict | None = None) -> "GaussianCopulaSynth":
        """Fit the copula model on training data.

        Args:
            df: Training DataFrame
            kinds: {column_name: kind_string} mapping
            seed: Random seed for DP noise
            dp: Optional {col: (epsilon, low, high)} for DP-Lite noise on marginals
        """
        dp = dp or {}
        rng = np.random.default_rng(seed)
        n = len(df)

        if n == 0:
            self._fitted = True
            return self

        self.cols = [c for c in df.columns if kinds.get(c) in MODELED]
        self.kinds = {c: kinds[c] for c in self.cols}
        self.null_rate = {c: float(df[c].isna().mean()) for c in self.cols}

        U_all = []  # uniform marginal scores for each column

        for c in self.cols:
            k = self.kinds[c]
            s = df[c]

            if k == "cat":
                self._fit_categorical(c, s, dp, rng)
                u = self._cat_to_uniform(c, s, n, rng)
            elif k == "bool":
                self._fit_boolean(c, s, dp, rng)
                u = self._bool_to_uniform(c, s, n, rng)
            else:
                self._fit_numeric(c, s, k, dp, rng)
                u = self._num_to_uniform(c, s, k, n, rng)

            U_all.append(np.clip(u, 1e-6, 1 - 1e-6))

        # Estimate correlation matrix in normal space
        if len(self.cols) > 1:
            Z = stats.norm.ppf(np.column_stack(U_all))
            Z = np.nan_to_num(Z, nan=0.0, posinf=3.0, neginf=-3.0)
            self.corr = _make_psd(np.corrcoef(Z, rowvar=False))
        elif len(self.cols) == 1:
            self.corr = np.ones((1, 1))
        else:
            self.corr = np.zeros((0, 0))

        self._fitted = True
        return self

    # ── Fit helpers ────────────────────────────────────────────────

    def _fit_categorical(self, c: str, s: pd.Series, dp: dict, rng):
        counts = s.dropna().astype(str).value_counts()
        cats = list(counts.index)
        vals = counts.to_numpy(dtype=np.float64)

        if c in dp:
            eps = dp[c][0] if isinstance(dp[c], (tuple, list)) else dp[c]
            vals = np.maximum(vals + rng.laplace(0, 1.0 / eps, vals.size), 0.0)
            if vals.sum() <= 0:
                vals = np.ones_like(vals)

        probs = vals / vals.sum()
        cum = np.concatenate([[0.0], np.cumsum(probs)])
        self.marginals[c] = {"type": "cat", "cats": cats, "cum": cum, "probs": probs}

    def _fit_boolean(self, c: str, s: pd.Series, dp: dict, rng):
        mapped = s.map({True: 1, False: 0, "true": 1, "false": 0,
                        "True": 1, "False": 0, "1": 1, "0": 0,
                        "yes": 1, "no": 0, "Yes": 1, "No": 0})
        p = float(mapped.dropna().mean()) if mapped.dropna().any() else 0.5
        if c in dp:
            eps = dp[c][0] if isinstance(dp[c], (tuple, list)) else dp[c]
            p = np.clip(p + rng.laplace(0, 1.0 / eps), 0.01, 0.99)
        self.marginals[c] = {"type": "bool", "p": float(p)}

    def _fit_numeric(self, c: str, s: pd.Series, k: str, dp: dict, rng):
        x = _to_numeric(s, k)
        ok = ~np.isnan(x)
        x_ok = x[ok]

        if len(x_ok) == 0:
            self.marginals[c] = {"type": "num", "q": np.zeros(len(Q)),
                                  "is_int": k in ("int", "money"),
                                  "is_date": k in ("date", "datetime"),
                                  "is_day_only": False}
            return

        if c in dp:
            eps, lo, hi = dp[c] if isinstance(dp[c], (tuple, list)) and len(dp[c]) == 3 else (dp[c], float(x_ok.min()), float(x_ok.max()))
            h, edges = np.histogram(np.clip(x_ok, lo, hi), bins=64, range=(lo, hi))
            h = np.maximum(h + rng.laplace(0, 1.0 / eps, h.size), 0.0)
            cdf = np.concatenate([[0.0], np.cumsum(h)]) / max(h.sum(), 1e-9)
            q = np.interp(Q, cdf, edges)
        else:
            q = np.quantile(x_ok, Q)

        is_day = (k in ("date", "datetime") and np.all(np.mod(x_ok, 86400) == 0))

        self.marginals[c] = {
            "type": "num",
            "q": q,
            "is_int": k in ("int", "money"),
            "is_date": k in ("date", "datetime"),
            "is_day_only": bool(is_day),
        }

    # ── Uniform transform helpers ─────────────────────────────────

    def _cat_to_uniform(self, c, s, n, rng):
        m = self.marginals[c]
        cats, cum = m["cats"], m["cum"]
        codes = pd.Categorical(s.astype(str).where(s.notna()), categories=cats).codes
        ci = np.clip(codes, 0, len(cats) - 1)
        u = cum[ci] + rng.random(n) * (cum[ci + 1] - cum[ci])
        return np.where(codes < 0, rng.random(n), u)

    def _bool_to_uniform(self, c, s, n, rng):
        p = self.marginals[c]["p"]
        mapped = s.map({True: 1, False: 0, "true": 1, "false": 0,
                        "True": 1, "False": 0, "1": 1, "0": 0,
                        "yes": 1, "no": 0}).to_numpy(dtype=float)
        u = np.where(mapped == 1, rng.uniform(1 - p, 1.0, n),
                     np.where(mapped == 0, rng.uniform(0, 1 - p, n), rng.random(n)))
        return u

    def _num_to_uniform(self, c, s, k, n, rng):
        x = _to_numeric(s, k)
        ok = ~np.isnan(x)
        u = np.empty(n, dtype=np.float64)
        if ok.sum() > 0:
            u[ok] = (stats.rankdata(x[ok]) - 0.5) / max(ok.sum(), 1)
        u[~ok] = rng.random((~ok).sum())
        return u

    # ── Sampling ──────────────────────────────────────────────────

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        """Generate n synthetic rows preserving distributions and correlations."""
        if not self._fitted:
            raise RuntimeError("Must call fit() before sample()")
        if not self.cols:
            return pd.DataFrame(index=range(n))

        # Draw correlated normals → uniform via CDF
        z = rng.multivariate_normal(np.zeros(len(self.cols)), self.corr, size=n)
        u = stats.norm.cdf(z)

        out: dict[str, np.ndarray | list] = {}

        for j, c in enumerate(self.cols):
            m = self.marginals[c]
            uj = u[:, j]

            if m["type"] == "cat":
                idx = np.clip(np.searchsorted(m["cum"][1:], uj, side="right"),
                              0, len(m["cats"]) - 1)
                out[c] = np.array(m["cats"], dtype=object)[idx]

            elif m["type"] == "bool":
                out[c] = uj >= (1 - m["p"])

            else:  # numeric / date / money
                x = np.interp(uj, Q, m["q"])
                if m["is_date"]:
                    col = pd.Series(EPOCH + pd.to_timedelta(x, unit="s"))
                    out[c] = col.dt.floor("D") if m["is_day_only"] else col
                elif m["is_int"]:
                    out[c] = np.rint(x).astype(np.int64)
                else:
                    out[c] = np.round(x, 6)

        df = pd.DataFrame(out)

        # Inject nulls at original rates
        for c, rate in self.null_rate.items():
            if rate > 0 and c in df.columns:
                mask = rng.random(n) < rate
                df.loc[mask, c] = None

        return df

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def get_model_summary(self) -> dict:
        """Summary for debugging and the run manifest."""
        return {
            "columns_modeled": len(self.cols),
            "column_kinds": dict(self.kinds),
            "null_rates": dict(self.null_rate),
            "correlation_matrix_shape": list(self.corr.shape),
        }
