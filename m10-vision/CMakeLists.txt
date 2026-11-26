cmake_minimum_required(VERSION 3.16)
project(m10_vision VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(APPLE)
  set(CMAKE_OSX_DEPLOYMENT_TARGET "12.0" CACHE STRING "Minimum macOS deployment target")
endif()

add_library(m10_core native/common/m10_core.cpp)
target_include_directories(m10_core PUBLIC native/common)
target_compile_options(m10_core PRIVATE -Wall -Wextra -Wpedantic
  -Wno-unused-parameter)

add_executable(m10_sim native/app/main.cpp)
target_link_libraries(m10_sim PRIVATE m10_core)
target_compile_options(m10_sim PRIVATE -Wall -Wextra -Wpedantic
  -Wno-unused-parameter)

enable_testing()
add_executable(m10_core_tests tests/unit/test_core.cpp)
target_link_libraries(m10_core_tests PRIVATE m10_core)
target_compile_options(m10_core_tests PRIVATE -Wall -Wextra -Wpedantic
  -Wno-unused-parameter)
add_test(NAME m10_core_tests COMMAND m10_core_tests)

