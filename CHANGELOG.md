# CHANGELOG

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


[unreleased]: https://github.com/pymeasure/pyleco/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.2
[0.2.1]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.1
[0.2.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.2.0
[0.1.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.1.0
[alpha-0.0.1]: https://github.com/pymeasure/pyleco/releases/tag/alpha-0.0.1
