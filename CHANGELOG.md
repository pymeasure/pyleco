# CHANGELOG

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


[unreleased]: https://github.com/pymeasure/pyleco/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pymeasure/pyleco/releases/tag/v0.1.0
[alpha-0.0.1]: https://github.com/pymeasure/pyleco/releases/tag/alpha-0.0.1
