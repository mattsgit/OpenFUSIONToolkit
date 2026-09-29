#!/usr/bin/env bash
set -euo pipefail
source setup_env.sh
validation_mpi="$1"
test "$validation_mpi" = OFF || test "$validation_mpi" = ON
# Both configurations must use unchanged production numerical code.
git diff --exit-code 52f5f12cc7d5083426a5e84912802b29835ffbc9 -- src/base src/lin_alg src/physics src/fem src/grid src/ext_libs
git diff --exit-code 722a603 -- src
rm -rf builds/build_release
cmake -S src -B builds/build_release \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12 -DCMAKE_Fortran_COMPILER=gfortran-12 \
  -DCMAKE_Fortran_FLAGS="-g -fbacktrace" \
  -DOFT_BUILD_TESTS=ON -DOFT_BUILD_PYTHON=ON -DOFT_PACKAGE_PYTHON=OFF \
  -DHDF5_ROOT="$PWD/builds/hdf5-install" \
  -DOFT_USE_MPI="$validation_mpi" -DBLA_VENDOR=OpenBLAS \
  -DOFT_UMFPACK_ROOT="$PWD/builds/suitesparse-install" \
  -DOFT_ARPACK_ROOT=/usr -DOFT_SUPERLU_ROOT=/usr -DSUPERLU_INCLUDE_DIR=/usr/include/superlu
cmake --build builds/build_release --target test_taylor_green_2d -j 4
