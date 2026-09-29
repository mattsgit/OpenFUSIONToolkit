# SPDX-License-Identifier: LGPL-3.0-only
"""Add observation-only logging to the one-step inner GMRES for diagnostics."""
from pathlib import Path

source = Path('src/lin_alg/native_solvers.F90')
text = source.read_text()
needle = '    h(i+1,i)=SQRT(w%dot(w))\n'
assert text.count(needle) == 2, 'Unexpected GMRES source layout'
observation = ('    IF(its==1)WRITE(*,\'(A,I0,2ES24.15)\') &\n'
               '      "DIAG_INNER_ARNOLDI ",i,h(i,i),h(i+1,i)\n')
source.write_text(text.replace(needle, needle + observation, 1))
