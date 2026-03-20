# General
 - You must follow the test-driven design, when finishing the implementation of one component <COMPONENT> under the application <APP>, you must create unit tests under <PROJECT_ROOT>/tests/<APP>/<COMPONENT> to make sure that the component is well-implemented and functioning. 
 - If some of the APIs need mock components and interfaces, you should do proper mocking. 

# Coding style
 - You should put constants and settings that belong to the same application into a single module under that application (can contain one or multiple files, whichever fits better). Don't put some settings here and some settings there, it'll be hard to locate and manage them.

# Application Specific Settings
## Scholar inbox curate
### Access to scholar-inbox 
  - user name: jerryjcw@gmail.com
  - pass: P746ndHr
  - The website seems to be protected by cloudflair real-human test.

# Test Execution
- Before running a full test suite, consider whether it might exceed the default 2-minute Bash timeout. If so, use an explicit `timeout` parameter (e.g., `timeout=300000` for 5 minutes).
- If a Bash command appears to time out or gets backgrounded unexpectedly, do NOT retry the same command repeatedly. Instead: (1) check if the process is still running (`ps aux | grep ...`), (2) check the output file if it was backgrounded, (3) diagnose the root cause (e.g., timeout too short, hanging test) before retrying.
- For quick validation, run only the specific test files relevant to your changes rather than the full suite. Run the full suite once at the end with a sufficient timeout.