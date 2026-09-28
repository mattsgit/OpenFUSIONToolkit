"""Apply the proposed residual-ordering change only inside this diagnostic job."""
from pathlib import Path

path = Path('src/physics/xmhd_2d.F90')
source = path.read_text()
start = source.index('  !---Add local values to full vector\n  IF(incomp) THEN')
end = source.index('  DO jr=1,oft_blagrange%nce\n    !$omp atomic\n    n_res', start)
block = source[start:end]
assert block.count('!$omp ordered') == 3
assert block.count('!$omp end ordered') == 2
block = block.replace('      !$omp ordered\n', '').replace('      !$omp end ordered\n', '')
block = block.replace('  !$omp ordered\n', '')
block = block.replace('  IF(incomp) THEN', '  !$omp ordered\n  IF(incomp) THEN')
path.write_text(source[:start] + block + source[end:])
