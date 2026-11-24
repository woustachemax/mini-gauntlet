# Importing the provider modules runs their @check decorators, which fills the registry.
from app.scanner.checks import aws, azure, gcp  # noqa: F401
