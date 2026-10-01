"""Single source of truth for the Jeffy Toolkit version.

The project follows Semantic Versioning (https://semver.org):

* MAJOR - incompatible API changes (renamed/removed public functions).
* MINOR - new tools or features added in a backwards compatible way.
* PATCH - bug fixes only.

Remember to add an entry to ``CHANGELOG.md`` whenever this number changes.
"""

__version__ = "1.0.0"

VERSION_INFO = tuple(int(part) for part in __version__.split("."))
