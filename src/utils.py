import random
import os
import logging
import numpy as np 
import torch       

log = logging.getLogger(__name__)

def set_deterministic_seed(seed: int = 42) -> None:
    """
    Erzwingt deterministische Abläufe für reproduzierbare Experimente.
    Setzt den Seed für Python, OS, Numpy und PyTorch.
    """
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8' # Nötig für deterministische CUDA-Operationen
    
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    # torch.use_deterministic_algorithms(True) # Optional: Wirft Fehler, falls eine Operation nicht deterministisch ausgeführt werden kann.
    
    log.info(f"[Init] Globaler Random Seed auf {seed} fixiert (inkl. PyTorch/CUDA).")