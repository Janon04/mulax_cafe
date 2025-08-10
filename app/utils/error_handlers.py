"""
Enhanced error handling for Mulax Cafe application with comprehensive logging
and conditional API/HTML response support.
"""

import logging
from datetime import datetime
from flask import render_template, request, jsonify, current_app
from werkzeug.exceptions import HTTPException
from flask_login import current_user


def register_error_handlers(app):
    """Register custom error handlers for the Flask application."""

    def is_api_request():
        """Determine if the current request expects a JSON response."""
        return request.path.startswith("/api/") or request.accept_mimetypes.accept_json

    def api_error_response(message, code, details=None):
        """Create a standardized API error response."""
        response = {
            "error": message,
            "code": code,
            "endpoint": request.path,
            "method": request.method
        }
        if details and current_app.config.get("DEBUG", False):
            response["details"] = details
        return jsonify(response), code

    def log_error(error, critical=False):
        """Log the error with detailed context."""
        logger = logging.getLogger(__name__)
        log_message = (
            f"{type(error).__name__}: {str(error)}\n"
            f"Path: {request.path}\n"
            f"Method: {request.method}\n"
            f"User: {getattr(current_user, 'id', 'Anonymous')}\n"
            f"IP: {request.remote_addr}"
        )

        if critical:
            logger.critical(log_message, exc_info=True)
        else:
            logger.error(log_message, exc_info=True)

    # ---- Specific Error Handlers ----

    @app.errorhandler(400)
    def bad_request_error(error):
        log_error(error)
        if is_api_request():
            return api_error_response("Bad request", 400, str(error))
        return render_template("errors/400.html", error=error), 400

    @app.errorhandler(403)
    def forbidden_error(error):
        log_error(error)
        if is_api_request():
            return api_error_response("Access forbidden", 403)
        return render_template("errors/403.html", error=error, current_user=current_user), 403

    @app.errorhandler(404)
    def not_found_error(error):
        log_error(error)
        if is_api_request():
            return api_error_response("Resource not found", 404)
        return render_template("errors/404.html", error=error, attempted_path=request.path), 404

    @app.errorhandler(500)
    def internal_error(error):
     if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        response = {
            "code": 500,
            "endpoint": request.path,
            "error": "Internal server error",
            "method": request.method
        }
        return render_template("errors/500.html", error=error), 500


    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Catch any unhandled exceptions."""
        if isinstance(error, HTTPException):
            return error  # Already handled by Flask

        log_error(error, critical=True)
        if is_api_request():
            return api_error_response("An unexpected error occurred", 500)
        return render_template("errors/500.html", error=error, timestamp=datetime.utcnow()), 500