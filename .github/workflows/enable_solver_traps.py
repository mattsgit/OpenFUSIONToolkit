# SPDX-License-Identifier: LGPL-3.0-only
"""Enable arithmetic traps after XML initialization, at the Newton solver entry."""
from pathlib import Path

path = Path('src/lin_alg/native_solvers.F90')
source = path.read_text().replace(
    'MODULE oft_native_solvers\n',
    'MODULE oft_native_solvers\nUSE, INTRINSIC :: IEEE_EXCEPTIONS\n', 1)
start = source.index('subroutine nksolver_apply(')
end = source.index('end subroutine nksolver_apply', start)
section = source[start:end].replace('DEBUG_STACK_PUSH\n', '''DEBUG_STACK_PUSH
!$omp parallel
CALL IEEE_SET_FLAG(IEEE_ALL,.FALSE.)
CALL IEEE_SET_HALTING_MODE(IEEE_INVALID,.TRUE.)
CALL IEEE_SET_HALTING_MODE(IEEE_DIVIDE_BY_ZERO,.TRUE.)
CALL IEEE_SET_HALTING_MODE(IEEE_OVERFLOW,.TRUE.)
!$omp end parallel
''', 1)
path.write_text(source[:start] + section + source[end:])

path = Path('src/base/oft_stitching.F90')
source = path.read_text()
start = source.index('function global_dp_r8(')
end = source.index('end function global_dp_r8', start)
section = source[start:end].replace('real(r8) :: c\n',
    'real(r8) :: c\nLOGICAL, ALLOCATABLE :: diagnostic_owned(:)\n', 1)
section = section.replace('IF(do_reduce)c=oft_mpi_sum(c)\n', '''IF(do_reduce)c=oft_mpi_sum(c)
IF(c<0.d0)THEN
  IF(ALL(a==b))THEN
    ALLOCATE(diagnostic_owned(n))
    diagnostic_owned=.TRUE.
    DO i=1,self%nbe
      IF(.NOT.self%leo(i))diagnostic_owned(self%lbe(i))=.FALSE.
    END DO
    WRITE(*,*)"DIAG_NEGATIVE_NORM",c,SUM(a*a,MASK=diagnostic_owned),MAXVAL(ABS(a)),n,self%nbe
    DEALLOCATE(diagnostic_owned)
  END IF
END IF
''', 1)
path.write_text(source[:start] + section + source[end:])
