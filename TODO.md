# Pending tasks

### Modularization of the features

- Split the requirements list for the base project and for each of the modules
- Create some mechanism for registering and enforcing dependencies between modules
- Update the build process to include only the required modules (and its requirements)
- Create a `live-client` library and use it as a dependency for the agent


# Wishlist

### User interface
- Create a module which provides a management web UI for the agent for controlling its settings (and maybe the list of enabled modules)
- Provide a web UI for the user to define new monitors and logic adapters, using predefined features exposed by the agent

### Remote logic adapters
- Create a logic adapter type which delegates the execution of `process` and `execute_action` to an external webservice (using ReST)
