"""Offline block-wise FP8 (e4m3, 128x128) quantization of Qwen3-30B-A3B-Instruct-2507, shard by shard on CPU.
Output follows the format of Qwen's official *-FP8 releases (quant_method fp8, weight_block_size [128,128],
'<name>.weight' in float8_e4m3fn plus '<name>.weight_scale_inv' float32 with w ~= w_fp8 * scale_inv).
Quantized: attention q/k/v/o_proj and expert gate/up/down_proj. Kept in bf16: embeddings, lm_head, norms, MoE router (mlp.gate).
Done offline because vLLM online FP8 would first materialise the full bf16 weights (~61 GB), more than the Worker has free."""
import json, os, re, shutil, sys, time
import torch
from safetensors import safe_open
from safetensors.torch import save_file
SRC, DST = sys.argv[1], sys.argv[2]
B = 128; FMAX = torch.finfo(torch.float8_e4m3fn).max
QUANT = re.compile(r"\.(self_attn\.(q|k|v|o)_proj|mlp\.experts\.\d+\.(gate|up|down)_proj)\.weight$")
os.makedirs(DST, exist_ok=True)

def quant(w):
    o, i = w.shape
    assert o % B == 0 and i % B == 0, (o, i)
    x = w.float().reshape(o // B, B, i // B, B).permute(0, 2, 1, 3)
    amax = x.abs().amax(dim=(2, 3)).clamp(min=1e-12)
    s = amax / FMAX
    q = (x / s[:, :, None, None]).clamp(-FMAX, FMAX).permute(0, 2, 1, 3).reshape(o, i).to(torch.float8_e4m3fn)
    return q.contiguous(), s.contiguous()

idx = json.load(open(os.path.join(SRC, "model.safetensors.index.json")))
new_map = {}; t0 = time.time(); nq = 0
for shard in sorted(set(idx["weight_map"].values())):
    out = {}
    with safe_open(os.path.join(SRC, shard), "pt") as f:
        for k in f.keys():
            t = f.get_tensor(k)
            if QUANT.search(k):
                q, s = quant(t); out[k] = q; out[k + "_scale_inv"] = s
                new_map[k] = shard; new_map[k + "_scale_inv"] = shard; nq += 1
            else:
                out[k] = t; new_map[k] = shard
    save_file(out, os.path.join(DST, shard), metadata={"format": "pt"})
    print(f"{shard} done ({time.time() - t0:.0f}s, {nq} quantized so far)", flush=True)
json.dump({"metadata": {}, "weight_map": new_map}, open(os.path.join(DST, "model.safetensors.index.json"), "w"), indent=1)
cfg = json.load(open(os.path.join(SRC, "config.json")))
gates = [f"model.layers.{l}.mlp.gate" for l in range(cfg["num_hidden_layers"])]
cfg["quantization_config"] = {"activation_scheme": "dynamic", "fmt": "e4m3", "quant_method": "fp8",
                              "weight_block_size": [B, B], "modules_to_not_convert": ["lm_head"] + gates}
json.dump(cfg, open(os.path.join(DST, "config.json"), "w"), indent=2)
for fn in os.listdir(SRC):
    if not fn.endswith(".safetensors") and fn not in ("config.json", "model.safetensors.index.json") and os.path.isfile(os.path.join(SRC, fn)):
        shutil.copy(os.path.join(SRC, fn), os.path.join(DST, fn))
print("DONE", nq, "tensors quantized", f"{time.time() - t0:.0f}s", flush=True)
