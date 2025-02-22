# CHANGELOG

## [0.4.2] 2025-02-22

### Fixed

* Fix trigger variable str breaks data_logger save ([111]https://github.com/pymeasure/pyleco/pull/111)

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.4.1...v0.4.2


## [0.4.1] 2025-02-12

_Increased test coverage and bug fixes._

### Changed

* Openrpc is optional (available via `openrpc` option) for Python 3.13 onwards.
* Rework rpc server ([#102](https://github.com/pymeasure/pyleco/pull/102))
* Increase test coverage ([#104](https://github.com/pymeasure/pyleco/pull/104))
* Change copyright year to 2025 ([#106](https://github.com/pymeasure/pyleco/pull/106))

### Added

* Add support for Python 313 ([#98](https://github.com/pymeasure/pyleco/pull/98))
* Add supported python versions to readme via shield. ([#103](https://github.com/pymeasure/pyleco/pull/103))

### Fixed
* Fix open rpc ([#95](https://github.com/pymeasure/pyleco/pull/95))
* Fix ruff action ([#99](https://github.com/pymeasure/pyleco/pull/99))
* Fix erroneous timeout argument in PipeHandler ([#109](https://github.com/pymeasure/pyleco/pull/109))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.4.0...v0.4.1


## [0.4.0] 2024-06-19

_Binary data handling facilitated with utility functions._

### Changed
* Proxy_server stops if binding failed ([#86](https://github.com/pymeasure/pyleco/pull/86))

### Added

* Add convenience functions for using additional frames for binary payload ([#82](https://github.com/pymeasure/pyleco/pull/82))
* Improve getting_started and readme documentation ([#80](https://github.com/pymeasure/pyleco/pull/80))
* Add RELEASE.md ([#79](https://github.com/pymeasure/pyleco/pull/79))
* Add locking actor ([#84](https://github.com/pymeasure/pyleco/pull/84))

### Fixed

* Fix listener documentation ([#88](https://github.com/pymeasure/pyleco/pull/88))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.3.2...v0.4.0


## [0.3.2] 2024-05-07

### Fixed

* Fix dependency on outdated UUIDv7 generating library to `uuid6` package ([#75](https://github.com/pymeasure/pyleco/pull/75))
* Fix codecov CI ([#73](https://github.com/pymeasure/pyleco/pull/73))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.3.1...v0.3.2


## [0.3.1] 2024-04-12

### Fixed

* Fix `Coordinator` to not use period in hostname as namespace ([#69](https://github.com/pymeasure/pyleco/pull/69))
* Fix `DataLogger` timer ([#70](https://github.com/pymeasure/pyleco/pull/70))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.3.0...v0.3.1


## [0.3.0] 2024-03-13

_Use self defined objects instead of jsonrpc2-objects and jsonrpc2-pyclient._

### Changed

- Rename `cls` parameter to `device_class` in `Actor` and `TransparentDirector`.
- Substitute `jsonrpc2-objects` and `jsonrpc2-pyclient` by self written objects ([#65](https://github.com/pymeasure/pyleco/pull/65))
- Move error definitions from `pyleco.errors` to `pyleco.json_utils.errors` ([#63](https://github.com/pymeasure/pyleco/pull/63))
- Move `pyleco.errors.CommunicationError` to `pyleco.json_utils.errors` ([#63](https://github.com/pymeasure/pyleco/pull/63))
- Deprecate `generate_error_with_data` in favor of `DataError.from_error` class method ([#63](https://github.com/pymeasure/pyleco/pull/63))
- Python requirement lowered to Python 3.8 ([#64](https://github.com/pymeasure/pyleco/pull/64))
- Rework the message buffer in the base communicator and harmonize with pipe handler's buffer ([#66](https://github.com/pymeasure/pyleco/pull/66))
- Bump CI actions versions for node.js 20 ([#62](https://github.com/pymeasure/pyleco/pull/62))

### Added

- Add __future__.annotations to all files, which need it for annotations for Python 3.7/3.8.
- Add self written `RPCServer` as alternative to openrpc package.

### Deprecated

- Deprecate `pyleco.errors` in favor of `json_utils.errors` and `json_utils.json_objects`.
- Deprecate to use `CommunicatorPipe.buffer`, use `message_buffer` instead.

### Fixed

- Fix Listener's communcator did not know, when listening stopped ([#67](https://github.com/pymeasure/pyleco/pull/67))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.2.2...v0.3.0


## [0.2.2] - 2024-02-14

### Fixed

- Fix Communicator to distinguish correctly different json rpc messages ([#57](https://github.com/pymeasure/pyleco/issues/57))
- Fix MessageHandler not distinguish correctly batch requests ([#56](https://github.com/pymeasure/pyleco/issues/56))
- Bump setup-python action version to v5

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.2.1...v.0.2.2


## [0.2.1] - 2024-02-13

### Fixed

- Fix BaseCommunciator to hand over message, if it is an error message (#55)

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.2.0...v.0.2.1


## [0.2.0] - 2024-02-13

_Several deprecated parts are removed and inner workings are changed._

### Changed

- **Breaking:** change `MessageHandler.handle_commands` to `handle_message` ([#44](https://github.com/pymeasure/pyleco/pull/44))
- **Breaking:** change PipeHandler inner workings of handling messages ([#44](https://github.com/pymeasure/pyleco/pull/44))
- Add `BaseCommunicator` as a base class for Communicator and MessageHandler ([#48](https://github.com/pymeasure/pyleco/pull/48))
- Refactor the Coordinator `handle_commands` ([#50](https://github.com/pymeasure/pyleco/pull/50))

### Added

- Add the `Coordinator`, the `proxy_server`, and the `starter` as scripts to the command line ([#53](https://github.com/pymeasure/pyleco/pull/53))

### Removed

- **Breaking:** remove `Coordinator.ask_raw` (#48)
- **Breaking:** remove legacy subscription messages from extended message handler (#48)

### Fixed

- Fix DataLogger to start a timer, even if not specified explicitly ([#51](https://github.com/pymeasure/pyleco/pull/51))

**Full Changelog**: https://github.com/pymeasure/pyleco/compare/v0.1.0...v.0.2.0


## [0.1.0] - 2024-02-01

### Changed

- Change message and protocols according to LECO change ([`9d74731da`](https://github.com/pymeasure/pyleco/commit/9d74731da06d147b1773f1f411bd943a36b4a83d)) (@BenediktBurger)
- Change Coordinator's `fname` to `full_name` ([`f3564c0`](https://github.com/pymeasure/pyleco/commit/f3564c08f04ed63bbab5b1100560e7b50239d83c)) (@BenediktBurger)

### Added

- Add compatibility with Python 3.9 ([`18abb87`](https://github.com/pymeasure/pyleco/commit/18abb87fea259f9e87411d88cca92a886bbd62b4)) (@BenediktBurger)
- Add compatibility with Python 3.12 ([#22](https://github.com/pymeasure/pyleco/pull/22)) (@BenediktBurger)
- Add more tests.
- Add more functionality to internal protocol and test suite ([`42e107c5cb90`](https://github.com/pymeasure/pyleco/commit/42e107c5cb90704dbb99ef1c5a50be739f3acf85)) (@BenediktBurger)
- Add Communicator functionality to the MessageHandler by distinguishing messages. (`9b0cc42`, `45913a5`, `97d902b`) (@BenediktBurger)
- Add CI for testing ([#22](https://github.com/pymeasure/pyleco/pull/22), [#7](https://github.com/pymeasure/pyleco/pull/7), #34, #29, #26) (@BenediktBurger)
- Add codecov code coverage calculation to CI ([#32](https://github.com/pymeasure/pyleco/pull/32)) (@BenediktBurger)
- Add `GETTING_STARTED.md` with a tutorial ([`000245b`](https://github.com/pymeasure/pyleco/commit/000245b7d693336a36b3f8bb5b0d0fe13a1bd6a7)) ([#24](https://github.com/pymeasure/pyleco/pull/24)) (@BenediktBurger, @bklebel)

### Removed

- **Breaking:** remove deprecated `Publisher` (use `DataPublisher` instead); move `Republisher` and `ExtendedPublisher` to pyleco-extras package ([#33](https://github.com/pymeasure/pyleco/pull/33)) (@BenediktBurger)
- **Breaking:** remove deprecated `call_method_rpc` and `call_method_rpc_async`

### Fixed

- Fix typos, also in variable / method names


## [alpha-0.0.1] - 2023-12-12

_Initial alpha version, complies with [LECO protocol alpha-0.0.1](https://github.com/pymeasure/leco-protocol/releases/tag/alpha-0.0.1)_

### New Contributors

@BenediktBurger, @bilderbuchi, @bklebel


[unreleased]: https://github.com/pymeasure/pyleco/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/pymeasure/pyleco/releases/tag/v0.4.2
[0.4.1]: https://github.com/pymeasure/pyleco/releases/tag/v0.4.1
[0.4.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.4.0
[0.3.2]: https://github.com/pymeasure/pyleco/releases/tag/v0.3.2
[0.3.1]: https://github.com/pymeasure/pyleco/releases/tag/v0.3.1
[0.3.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.3.0
[0.2.2]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.2
[0.2.1]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.1
[0.2.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.0
[0.1.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.1.0
[alpha-0.0.1]: https://github.com/pymeasure/pyleco/releases/tag/alpha-0.0.1
