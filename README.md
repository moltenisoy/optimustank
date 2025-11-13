# OPTIMUSTANK

**OPTIMUSTANK** is a sophisticated system optimizer designed to enhance the performance and stability of your computer. It provides a comprehensive suite of tools for managing CPU, memory, disk, network, and GPU resources, all wrapped in a professional and intuitive graphical user interface.

## 🚀 Features

*   **Real-Time Monitoring**: Keep track of your system's health with a real-time dashboard that displays key performance metrics.
*   **Advanced Resource Management**: Optimize CPU, memory, disk, and network usage with intelligent algorithms and dynamic adjustments.
*   **GPU Optimization**: Get the most out of your graphics card with tools for overclocking, undervolting, and thermal management.
*   **Service and Task Management**: Keep your system running smoothly with automatic service recovery, task scheduling, and process cleaning.
*   **Extensible Architecture**: The modular design allows for easy extension and customization to suit your specific needs.
*   **Cross-Platform Support**: While primarily designed for Windows, it also includes support for Linux environments.

## 🛠️ Getting Started

### Prerequisites

*   Python 3.8 or higher
*   Required Python packages:
    - psutil (system monitoring)
    - pydantic (configuration validation)
    - watchdog (file system monitoring)
    - Additional packages may be needed for specific features

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/moltenisoy/optimustank.git
    cd optimustank
    ```

2.  **Install dependencies**:
    ```bash
    pip install psutil pydantic watchdog
    ```

### Running the Application

To start the optimizer, run the `main.py` script:

```bash
python main.py
```

## 🧪 Running Tests

The project includes a suite of tests to ensure the stability and correctness of the code. To run the tests, use the following command:

```bash
python tests.py
```

## 🤝 Contributing

Contributions are welcome! If you have any ideas, suggestions, or bug reports, please open an issue or submit a pull request.

## 📚 Documentation

For comprehensive optimization recommendations including basic, deep, kernel, and hardware optimizations, see [RECOMMENDATIONS.md](RECOMMENDATIONS.md).

## 🏗️ Project Structure

The codebase has been refactored into a clean, modular structure:

- **Core modules** (`core_events.py`, `memory_utils.py`, `reliability_utils.py`, `logging_profiling.py`, `platform_threading.py`): Consolidated utility modules
- **Gestores** (10 manager modules): CPU, Memory, Disk, Network, GPU, Services, Tasks, Kernel, Energy, and Modules management
- **Base infrastructure**: `base_gestor_Version2.py`, `dependency_container.py`, `main.py`
- **Testing**: `test_framework.py`, `tests.py`

Total: 21 Python files (consolidated from 30+ original files)

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for more details.
