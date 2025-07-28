from datetime import datetime
from flask import current_app
from app.models import Requisition

def validate_requisition_edit(requisition_id, user):
    """
    Validate if a requisition can be edited
    Returns:
        Tuple: (can_edit: bool, message: str)
    """
    requisition = Requisition.query.get(requisition_id)
    if not requisition:
        return False, "Requisition not found"
    
    if requisition.user_id != user.id:
        return False, "You can only edit your own requisitions"
    
    if requisition.status != 'pending':
        return False, "Only pending requisitions can be edited"
    
    edit_window = current_app.config.get('REQUISITION_EDIT_WINDOW', 120)  # seconds
    time_elapsed = (datetime.utcnow() - requisition.date).total_seconds()
    
    if time_elapsed > edit_window:
        return False, f"Edit window expired (max {edit_window//60} minutes)"
    
    return True, ""

def validate_product_data(data):
    """Validate product form data"""
    errors = {}
    
    if not data.get('name'):
        errors['name'] = "Product name is required"
    
    if not data.get('category'):
        errors['category'] = "Category is required"
    
    if not data.get('unit'):
        errors['unit'] = "Unit of measurement is required"
    
    try:
        float(data.get('current_stock', 0))
    except ValueError:
        errors['current_stock'] = "Invalid stock value"
    
    try:
        float(data.get('unit_price', 0))
    except ValueError:
        errors['unit_price'] = "Invalid price value"
    
    return errors if errors else None