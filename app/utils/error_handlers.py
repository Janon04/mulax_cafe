"""
Enhanced error handling for Mulax Cafe application
"""
from flask import render_template, request, jsonify, current_app
from werkzeug.exceptions import HTTPException
import logging

def register_error_handlers(app):
    """Register error handlers for the application"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("errors/404.html"), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        current_app.logger.error(f"Server Error: {error}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Access forbidden"}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle unexpected exceptions"""
        if isinstance(e, HTTPException):
            return e
        
        current_app.logger.error(f"Unhandled Exception: {e}", exc_info=True)
        if request.path.startswith("/api/"):
            return jsonify({"error": "An unexpected error occurred"}), 500
        return render_template("errors/500.html"), 500

