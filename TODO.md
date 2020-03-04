# Pending tasks

### Modularization of the features

- (done) Create a `live-client` library and use it as a dependency for the agent
- (done) Split the requirements list for the base project and for each of the modules
- Create some mechanism for registering and enforcing dependencies between modules
- Update the build process to include only the required modules (and its requirements)
- Create some mechanism for defining the settings format for each of the modules
- Create a mechanism (similar to `live-client`'s `check_live_features`) which validates which features are available for a given settings file
- Define how users of this library should work with it, including the processes for development, test, build and deploy of a module


# Wishlist

### User interface
- Create a command for packaging a module as a zipped python module (`build-module`)

- Create a module which provides a management web UI for controlling the agent's settings (including the list of enabled modules) and the hability to upload a zipped module
  - Implemented in flask
  - Default settings exposing only the management UI
  - Credentials defined during the build process

- Provide a web UI for the user to define new monitors and logic adapters, using predefined features exposed by the agent (similar to jupyterhub)


### Remote logic adapters
- Create a logic adapter type which delegates the execution of `process` and `execute_action` to an external webservice (using ReST)
