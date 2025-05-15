# This file makes quality_assessment a Python package

from flask import Blueprint

# Create a Blueprint for the quality assessment feature
# We'll import routes and other components here later
quality_bp = Blueprint(
    'quality_assessment',
    __name__,
    template_folder='templates',
    # url_prefix='/qa' # Optional: if you want all routes in this BP to be prefixed
)

# Import routes after blueprint definition to avoid circular imports
from . import routes 