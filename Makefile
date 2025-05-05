# Makefile for fast_ingest.cpp

# Compiler and flags
CXX = g++
CXXFLAGS = -std=c++17 -Wall -O3
LIBS = -lcurl

# Target executable
TARGET = fast_ingest

# Source files
SRCS = fast_ingest.cpp

# Object files
OBJS = $(SRCS:.cpp=.o)

# Default target
all: $(TARGET)

# Build target
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

# Compile source files
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean up build artifacts
clean:
	rm -f $(TARGET) $(OBJS)

.PHONY: all clean