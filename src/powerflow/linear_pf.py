"""
linear_pf.py - Sensitivity Coefficient 기반 선형화 조류계산 (LPF)

각 노드 주입전력 변화 → 전압·전류 변화를 1차 선형 근사하여
MILP 계획 모델에 전압/전류 운영 제약을 부과한다.

핵심 수식:
    |v_t| ≈ A_v · [p; q] + b_v      (노드 전압 크기)
    |i_l| ≈ A_i · [p; q] + b_i      (선로 전류 크기)

참고:
    Christakou et al. (2013) IEEE Trans. Smart Grid
    Gupta et al. (2023) Applied Energy

가정 / Limitation:
    - flat start(전압 1.0pu) 기준 단일 선형화 → 운영점에서 멀어지면 오차 증가
    - 전류 크기 선형화는 전압 크기 항만 근사 (위상각 항 단순화)
"""

import numpy as np

from src.data_process.network import (
    NUM_NODES, LINE_DATA, SLACK_BUS, BASE_Z,
)


class LinearPowerFlow:
    """flat start 기준 sensitivity coefficient 계산."""

    def __init__(self, v0_pu=None, verbose=False):
        self.verbose = verbose
        self.N = NUM_NODES
        self.n_lines = len(LINE_DATA)

        self.Y = self._build_admittance()
        self.y_lines = self._line_admittances()

        self.v0 = np.ones(self.N) if v0_pu is None else np.array(v0_pu)
        self.theta0 = np.zeros(self.N)

        self.A_v = self.b_v = None     # 전압 감도
        self.A_i = self.b_i = None     # 전류 감도

        self._compute_sensitivity()

    # ── 내부 메서드 ──────────────────────────────────────
    def _build_admittance(self):
        # LINE_DATA 임피던스는 [Ω] → 어드미턴스 계산 전 per-unit 변환(÷BASE_Z).
        # (전력 주입이 pu 이므로 임피던스도 pu 여야 전압·전류 감도가 정합)
        Y = np.zeros((self.N, self.N), dtype=complex)
        for line in LINE_DATA:
            i, j = int(line[0]), int(line[1])
            y = 1.0 / complex(line[2] / BASE_Z, line[3] / BASE_Z)
            Y[i, i] += y
            Y[j, j] += y
            Y[i, j] -= y
            Y[j, i] -= y
        return Y

    def _line_admittances(self):
        # [Ω] → pu 변환 후 어드미턴스 (전류 감도 pu 정합)
        return np.array([1.0 / complex(l[2] / BASE_Z, l[3] / BASE_Z) for l in LINE_DATA])

    def _compute_sensitivity(self):
        """Jacobian 분해로 dV/dP, dV/dQ 및 전류 감도 계산."""
        N = self.N
        pq_idx = [i for i in range(N) if i != SLACK_BUS]
        n_pq = len(pq_idx)

        G = np.real(self.Y)
        B = np.imag(self.Y)
        v = self.v0.copy()
        th = self.theta0.copy()

        # ── 전력조류 Jacobian (PQ 노드 기준) ──
        J = np.zeros((2 * n_pq, 2 * n_pq))
        for idx_i, i in enumerate(pq_idx):
            vi = v[i]
            for idx_j, j in enumerate(pq_idx):
                vj = v[j]
                th_ij = th[i] - th[j]
                if i == j:
                    Pi = sum(v[i] * v[k] * (G[i, k] * np.cos(th[i] - th[k])
                             + B[i, k] * np.sin(th[i] - th[k]))
                             for k in range(N) if k != i)
                    Qi = sum(v[i] * v[k] * (G[i, k] * np.sin(th[i] - th[k])
                             - B[i, k] * np.cos(th[i] - th[k]))
                             for k in range(N) if k != i)
                    J[idx_i, idx_j]               = -Qi                           # dP/dθ (H_ii)
                    J[idx_i, idx_j + n_pq]        =  Pi / vi + 2 * G[i, i] * vi  # dP/dV (N_ii)
                    J[idx_i + n_pq, idx_j]        =  Pi                           # dQ/dθ (M_ii)
                    J[idx_i + n_pq, idx_j + n_pq] =  Qi / vi - 2 * B[i, i] * vi  # dQ/dV (L_ii)
                else:
                    J[idx_i, idx_j]              =  vi * vj * (G[i, j] * np.sin(th_ij) - B[i, j] * np.cos(th_ij))
                    J[idx_i, idx_j + n_pq]       =  vi * (G[i, j] * np.cos(th_ij) + B[i, j] * np.sin(th_ij))
                    J[idx_i + n_pq, idx_j]       = -vi * vj * (G[i, j] * np.cos(th_ij) + B[i, j] * np.sin(th_ij))
                    J[idx_i + n_pq, idx_j + n_pq] =  vi * (G[i, j] * np.sin(th_ij) - B[i, j] * np.cos(th_ij))

        try:
            J_inv = np.linalg.inv(J)
        except np.linalg.LinAlgError as exc:
            raise RuntimeError("Jacobian이 singular합니다. 계통 데이터를 확인하세요.") from exc

        dV_dP = J_inv[n_pq:, :n_pq]
        dV_dQ = J_inv[n_pq:, n_pq:]

        # A_v: 전압 = [dV/dP | dV/dQ] · [p; q] + b_v
        self.A_v = np.hstack([dV_dP, dV_dQ])
        self.b_v = v[pq_idx].copy()

        # ── 전류 감도 (전압 크기 변화 항 근사) ──
        A_i_rows, b_i_rows = [], []
        for l_idx, line in enumerate(LINE_DATA):
            i, j = int(line[0]), int(line[1])
            g_l = np.real(self.y_lines[l_idx])

            row_P = np.zeros(n_pq)
            row_Q = np.zeros(n_pq)
            if i != SLACK_BUS:
                ii = pq_idx.index(i)
                row_P += g_l * dV_dP[ii, :]
                row_Q += g_l * dV_dQ[ii, :]
            if j != SLACK_BUS:
                jj = pq_idx.index(j)
                row_P -= g_l * dV_dP[jj, :]
                row_Q -= g_l * dV_dQ[jj, :]
            A_i_rows.append(np.hstack([row_P, row_Q]))

            Vi = complex(v[i] * np.cos(th[i]), v[i] * np.sin(th[i]))
            Vj = complex(v[j] * np.cos(th[j]), v[j] * np.sin(th[j]))
            b_i_rows.append(abs(self.y_lines[l_idx] * (Vi - Vj)))

        self.A_i = np.array(A_i_rows)
        self.b_i = np.array(b_i_rows)

        if self.verbose:
            print(f"[LPF] A_v {self.A_v.shape}, A_i {self.A_i.shape} 계산 완료")

    # ── 공개 인터페이스 ──────────────────────────────────
    def get_voltage_sensitivity(self):
        """(A_v, b_v) 반환. A_v = [dV/dP | dV/dQ] (32×64)."""
        return self.A_v, self.b_v

    def get_q_voltage_sensitivity(self):
        """전압-무효전력 감도 dV/dQ (32×32) 반환."""
        n_pq = self.A_v.shape[0]
        return self.A_v[:, n_pq:], self.b_v

    def get_current_sensitivity(self):
        """(A_i, b_i) 반환. A_i = [dI/dP | dI/dQ] (32×64)."""
        return self.A_i, self.b_i


if __name__ == "__main__":
    lpf = LinearPowerFlow(verbose=True)
    print("b_v[:5]:", lpf.b_v[:5].round(4))
    print("b_i[:5]:", lpf.b_i[:5].round(4))
