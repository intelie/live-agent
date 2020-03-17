# Pending tasks

### Architecture and usage

- [x] Create a `live-client` library and use it as a dependency for the agent
- [x] Split the requirements list for the base project and for each of the modules
- [x] Create some support tools for the developer
  - [x] Create a command which bootstraps an agent (`create-agent`), adding the following:
    - `README.md`
    - `settings.json` with the basic structure
    - `tools` folder (same as `live-agent`'s)
    - `modules` folder (containing only an `__init__.py`)
  - [x] Create a command which bootstraps a new module (`add-agent-module`), asking for a name and adding a folder using the chosen name containing the default structure for a module:
    - `__init__.py` containing empty definitions for `PROCESSES` and `REQUIREMENTS`
    - `logic_adapters` folder
    - `monitors` folder
    - `datasources` folder
  - [x] Add a section to `live-agent`'s README with usage instructions for the scripts above
- [ ] Create some mechanism for defining the settings format for each of the modules (maybe `jsonschema` or `dataclasses`)
- [ ] Create a mechanism (_similar to/an extension of_ `live-client`'s `check_live_features`) which validates which features are available for a given settings file
- [ ] Define how users of this library should work with it, including the processes for development, test, build and deploy of a module:
  1. create the project's folder, virtualenv and repository
  1. add `live-agent` to the requirements
  1. install requirements
  1. run `create-agent`
  1. for each of the desired modules
     1. go to the `modules` folder and run `add-agent-module`
     1. implement the module(s)
     1. update the settings
     1. validate the settings with `check_live_features` (from `live-client`)
  1. build a release rpm
  1. deploy to the server
- [ ] _maybe:_ Update the build process to include only the required modules (and its requirements). Becomes less important (irrelevant) if each use-case has its own project and we don't have to juggle this.
- [ ] _maybe:_ Create some mechanism for registering and enforcing dependencies between modules. Also becomes less important if each use-case has its own project


### Use cases

- [ ] Create a project for the _Shell GameChanger_ features
- [ ] Create a project for the _torque and drag_ integration
- [ ] _maybe:_ Create a project for _Constellation's video-collector_
- [ ] _maybe:_ Create a project for _Propetro's isolation forest_


### User interface

- [ ] Create a module which provides a management web UI for controlling the agent's settings (including the list of enabled modules)
  - Implemented in flask
  - Default settings exposing only the management UI
  - Credentials defined during the build process
  - _question:_ How to control (start/stop/restart/add/remove/enable/disable) the processes managed by the agent? Always stop and restart everything?
- [ ] _maybe:_ Add the possibility to upload a zipped module to the management web UI
  - Create a command for packaging a module as a zipped python module (`build-module`)
  - _question:_ Do we need a sandbox or can we trust the developer? If we need a sandbox this requirement kills this feature.
- [ ] _maybe:_ Provide a web UI for the user to define new monitors and logic adapters, using predefined features exposed by the agent (similar to jupyterhub)


### Features

- [ ] Create a logic adapter type which delegates the execution of `process` and `execute_action` to an external webservice (using ReST)
- [ ] _maybe:_ Create a slack integration module
