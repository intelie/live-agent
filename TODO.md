# Pending tasks

### Architecture and usage

- _done:_ Create a `live-client` library and use it as a dependency for the agent
- _done:_ Split the requirements list for the base project and for each of the modules

- Define how users of this library should work with it, including the processes for development, test, build and deploy of a module:
  - Create a command which bootstraps an agent (`start-agent`), adding the following:
    - `modules` folder (containing only an `__init__.py` and a `README` with usage instructions for `add-agent-module`)
    - `tools` folder (same as `live-agent`'s)
    - `settings.json` with the basic structure
    - `README.md`
    - `run` script (same as `live-agent`'s)

  - Create a command which bootstraps a new module (`add-agent-module`), asking for a name and adding a folder using the chosen name containing the default structure for a module:
    - `__init__.py` containing an empty `PROCESSES` definition
    - `logic_adapters` folder
    - `monitors` folder
    - `datasources` folder

  - Add a section to `live-agent`'s README with usage instructions for the scripts above

- Create some mechanism for defining the settings format for each of the modules (maybe `jsonschema` or `dataclasses`)
- Create a mechanism (similar to `live-client`'s `check_live_features`) which validates which features are available for a given settings file. Maybe print these instructions after installing the lib?

- _maybe:_ Update the build process to include only the required modules (and its requirements). Becomes less important (irrelevant) if each use-case has its own project and we don't have to juggle this.
- _maybe:_ Create some mechanism for registering and enforcing dependencies between modules. Also becomes less important if each use-case has its own project


### User interface

- Create a module which provides a management web UI for controlling the agent's settings (including the list of enabled modules)
  - Implemented in flask
  - Default settings exposing only the management UI
  - Credentials defined during the build process

- _maybe:_ Add the possibility to upload a zipped module to the management web UI
  - Create a command for packaging a module as a zipped python module (`build-module`)

- _maybe:_ Provide a web UI for the user to define new monitors and logic adapters, using predefined features exposed by the agent (similar to jupyterhub)


### Remote logic adapters
- Create a logic adapter type which delegates the execution of `process` and `execute_action` to an external webservice (using ReST)
