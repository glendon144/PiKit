# 1. Raw tempo
kps_mean = float(max(0.0, x_smooth[0]))
bpm_live = int(round(self._kps_to_bpm(kps_mean)))

# 2. Temporal load  ← THIS MUST EXIST FIRST
load = self._temporal_load(x_smooth, bpm_live)

# 3. Override factor
factor = self.override.factor(now)
bpm_adj = int(round(max(BPM_MIN, min(BPM_MAX, bpm_live * factor))))

# 4. Temporal involution
inv = self._temporal_involution(load)

# 5. Apply involution effects
bpm_adj = int(round(
    max(BPM_MIN, min(BPM_MAX, bpm_adj * inv["bpm_bias"]))
))

tpm = int(round(self._bpm_to_tokens_per_minute(bpm_adj)))
if inv["tpm_cap"] is not None:
    tpm = min(tpm, inv["tpm_cap"])

