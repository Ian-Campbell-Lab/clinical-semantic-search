"""
Parallel embedding on TPU -- reference implementation using PyTorch/XLA.

This module fans out embedding computation across all available TPU cores
(typically 8 on a v4-7 or v5litepod-8) using data parallelism.  Each
worker loads its own copy of the model and processes a slice of the input.

PORTING NOTE: This module requires ``torch_xla``.  For GPU-based
deployments, replace with standard PyTorch DataParallel or a batched
CPU loop.  The key contract is:

    embed_parallel(chunk_df, model_path) -> chunk_df with 'embedding' column

where each embedding is a list of floats (L2-normalized).
"""

import logging

import torch
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)


def _worker(rank, args):
    """Per-TPU-core worker.  Loads model and processes its data slice."""
    import torch_xla.core.xla_model as xm

    from clinical_semantic_search.core.pooling import last_token_pool

    model_dir, batch_size, input_ids, attention_mask, out_shm = args

    device = xm.xla_device()
    xm.master_print(f"[rank {rank}] loading model on {device}...")
    model = AutoModel.from_pretrained(
        model_dir,
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    ).to(device).eval()

    N = input_ids.size(0)
    world_size = xm.runtime.world_size()
    per_rank = (N + world_size - 1) // world_size
    start = rank * per_rank
    end = min(start + per_rank, N)

    xm.master_print(f"[rank {rank}] handling rows [{start}, {end})")

    pbar = None
    if rank == 0:
        from tqdm import tqdm
        pbar = tqdm(total=end - start, desc="encode (rank 0 only)", dynamic_ncols=True)

    with torch.no_grad():
        for i in range(start, end, batch_size):
            sl = slice(i, min(i + batch_size, end))
            ids = {
                "input_ids": input_ids[sl].to(device, non_blocking=True),
                "attention_mask": attention_mask[sl].to(device, non_blocking=True),
            }
            out = model(**ids)
            emb = last_token_pool(out.last_hidden_state, ids["attention_mask"])
            xm.mark_step()
            xm.wait_device_ops()
            emb_cpu = emb.to(dtype=torch.float32, device="cpu")
            emb_cpu = F.normalize(emb_cpu, p=2, dim=1)
            out_shm[sl] = emb_cpu
            if pbar is not None:
                pbar.update(sl.stop - sl.start)

    xm.rendezvous("workers_done")
    if pbar is not None:
        pbar.close()


def embed_parallel(chunk_df, model_dir: str, batch_size: int = 256, max_len: int = 512):
    """Embed all chunks using data-parallel TPU workers.

    Parameters
    ----------
    chunk_df : pd.DataFrame
        Must contain a ``chunk`` column with text strings.
    model_dir : str
        Local path to the HuggingFace model directory.
    batch_size : int
        Per-worker batch size.
    max_len : int
        Maximum token length for tokenization.

    Returns
    -------
    The input DataFrame with an added ``embedding`` column (list of floats).
    """
    import torch_xla.distributed.xla_multiprocessing as xmp

    texts = chunk_df["chunk"].astype(str).tolist()
    logger.info("Tokenizing chunks.")

    tokenizer = AutoTokenizer.from_pretrained(model_dir, padding_side="left")
    tok = tokenizer(
        texts,
        max_length=max_len,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    if tok["attention_mask"].dtype != torch.int32:
        tok["attention_mask"] = tok["attention_mask"].to(torch.int32)
    logger.info("Finished tokenizing chunks.")

    input_ids = tok["input_ids"].share_memory_()
    attention_mask = tok["attention_mask"].share_memory_()

    cfg = AutoConfig.from_pretrained(model_dir)
    hidden = getattr(cfg, "hidden_size", 1024)

    N = input_ids.size(0)
    out_shm = torch.empty((N, hidden), dtype=torch.float32).share_memory_()

    args = (model_dir, batch_size, input_ids, attention_mask, out_shm)
    xmp.spawn(_worker, args=(args,), start_method="spawn")

    chunk_df["embedding"] = out_shm.numpy().tolist()
    return chunk_df
