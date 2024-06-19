# How to Contribute to PyLECO

You are welcome to contribute to PyLECO.

There are many ways, how to contribute:
- Share your experience with PyLECO,
- ask questions,
- suggest improvements,
- report bugs,
- improve the documentation,
- fix bugs,
- add new features
- ...


## Suggestions / Questions / Bugs

If you have a suggestion, a question, or found a bug, please open an `issue` on our [github issues](https://github.com/pymeasure/pyleco/issues) page or on the discussions page.

### Bug reports

For technical suggestions, questions, or bug reports, please try to be as descriptive as possible in order to allow others to help you better.

For a bug report, the following information is a good start:
- Which PyLECO version do you use? installed from PyPI / conda-forge or from the current main branch from github?
- Python version
- Operating system

If you are able, you can try to fix the bug and open a pull request, see below.

### Show and Tell

You are especially welcome to share, how you use PyLECO in the [show-and-tell discussions](https://github.com/pymeasure/pyleco/discussions/categories/show-and-tell).


## New Features / Bug Fixes

If you want to add a new feature, please open an issue first in order to discuss the feature and ideas of its implementation.

### Development

Once the general idea is tied down, you can open a pull request (towards the `main` branch) with your code.
We encourage to open a pull request early on, to incorporate review comments from the beginning.

For development, we recommend _test driven development_, that is writing tests and the features at the same time supporting each other.

For example for a bug fix:
1. Write a test for the expected behaviour, which will fail (as there is a bug),
2. fix the code, such that the bug is fixed and the test succeeds,
3. refactor the code.

### Test Framework

We use pytest as our test framework.
All tests are in the `tests` folder.
Each module has its own file with unit tests in a similarly named structure, for example `pyleco/core/message.py` has the `tests/core/test_message.py` test file.

There is a special folder, `tests/acceptance_tests` with acceptance tests, that are tests, which test several modules working together.

The module [`pymeasure.test`](pyleco/test.py) offers fake classes, e.g. a fake zmq Socket, in order to facilitate writing tests.
