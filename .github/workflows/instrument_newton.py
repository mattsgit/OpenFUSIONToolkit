# SPDX-License-Identifier: LGPL-3.0-only
"""Add observation-only diagnostics to the existing Newton/GMRES implementation."""
from pathlib import Path

path = Path('src/lin_alg/native_solvers.F90')
source = path.read_text()
replacements = {
    '    h(i+1,i)=SQRT(w%dot(w))\n':
        '    h(i+1,i)=SQRT(w%dot(w))\n'
        '    IF(h(i+1,i)==0.d0.AND.oft_env%head_proc)WRITE(*,*)"DIAG_GMRES_ZERO_ARNOLDI",i,nrits,nits,SQRT(gg)\n',
    '    uu=u%dot(u)\n':
        '    uu=u%dot(u)\n'
        '    IF(i==0.AND.oft_env%head_proc)WRITE(*,*)"DIAG_NK_INITIAL",SQRT(res),SQRT(uu),self%atol\n',
    '    if(sback<1.d-8)THEN\n':
        '    if(sback<1.d-8)THEN\n'
        '      IF(oft_env%head_proc)WRITE(*,*)"DIAG_NK_BACKTRACK",i,SQRT(res),SQRT(resp),SQRT(uu),sback\n',
    '  IF(i==its)self%cits=-1\n':
        '  IF(i==its)THEN\n'
        '    self%cits=-1\n'
        '    IF(oft_env%head_proc)WRITE(*,*)"DIAG_NK_LIMIT",i,SQRT(res),self%atol\n'
        '  END IF\n',
    '  IF(self%J_inv%cits<0)THEN\n':
        '  IF(self%J_inv%cits<0)THEN\n'
        '    IF(oft_env%head_proc)WRITE(*,*)"DIAG_NK_LINEAR",i,self%J_inv%cits,self%J_inv%its,SQRT(res),self%atol,SQRT(v%dot(v))\n',
}
for original, diagnostic in replacements.items():
    routine = 'gmres_solver_apply' if original.startswith('    h(i+1,i)') else 'nksolver_apply'
    start = source.index('subroutine ' + routine + '(')
    end = source.index('end subroutine ' + routine, start)
    section = source[start:end]
    if section.count(original) != 1:
        raise RuntimeError('Unexpected source match count: ' + original)
    source = source[:start] + section.replace(original, diagnostic) + source[end:]
path.write_text(source)
