from datetime import datetime, time
from app.models import Shift

def get_current_shift():
    """Determine which shift is currently active based on system time."""
    now = datetime.now().time()
    
    # Get all active shifts ordered by start time
    shifts = Shift.query.filter_by(is_active=True).order_by(Shift.start_time).all()
    
    for shift in shifts:
        if shift.start_time <= now < shift.end_time:
            return shift
    
    # Handle overnight shifts (if any)
    for shift in shifts:
        if shift.start_time > shift.end_time:  # Overnight shift
            if now >= shift.start_time or now < shift.end_time:
                return shift
    
    return None  # No active shift found