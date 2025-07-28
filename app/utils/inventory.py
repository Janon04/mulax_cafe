from datetime import datetime, timedelta
from app.models import db, Product, StockMovement

def update_stock(product_id, quantity, movement_type, notes=None, user_id=None):
    """
    Update product stock and record movement
    Args:
        product_id: ID of the product
        quantity: Quantity to add/remove
        movement_type: 'purchase', 'usage', or 'adjustment'
        notes: Optional notes about the movement
        user_id: ID of user making the change
    Returns:
        Tuple: (success: bool, message: str)
    """
    try:
        product = Product.query.get(product_id)
        if not product:
            return False, "Product not found"
        
        opening_stock = product.current_stock
        
        if movement_type == 'purchase':
            product.current_stock += quantity
        elif movement_type == 'usage':
            if product.current_stock < quantity:
                return False, f"Insufficient stock. Only {product.current_stock} {product.unit} available"
            product.current_stock -= quantity
        elif movement_type == 'adjustment':
            product.current_stock = quantity
        else:
            return False, "Invalid movement type"
        
        # Record the movement
        movement = StockMovement(
            product_id=product.id,
            opening_stock=opening_stock,
            stock_in=quantity if movement_type == 'purchase' else 0,
            stock_out=quantity if movement_type == 'usage' else 0,
            closing_stock=product.current_stock,
            movement_type=movement_type,
            notes=notes,
            user_id=user_id
        )
        
        db.session.add(movement)
        db.session.commit()
        return True, "Stock updated successfully"
    
    except Exception as e:
        db.session.rollback()
        return False, f"Error updating stock: {str(e)}"

def get_low_stock_items(threshold=5):
    """Return products with stock below threshold"""
    return Product.query.filter(Product.current_stock < threshold).order_by(Product.current_stock).all()

def get_stock_movements(product_id=None, days=30):
    """
    Get stock movements with optional filters
    Args:
        product_id: Filter by product
        days: Number of days to look back
    """
    query = StockMovement.query
    if product_id:
        query = query.filter_by(product_id=product_id)
    
    # if days:
    #     cutoff_date = datetime.utcnow() - timedelta(days=days)
    #     query = query.filter(StockMovement.date >= cutoff_date)
    
    return query.order_by(StockMovement.date.desc()).all()