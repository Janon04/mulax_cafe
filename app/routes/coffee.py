from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response, jsonify, send_file
from flask_login import login_required, current_user
from flask import render_template_string
from app.models import Order, CoffeeSale, Product, Waiter, StockMovement, Shift
from app import db
from sqlalchemy import func
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl import Workbook
from xhtml2pdf import pisa
import pytz

bp = Blueprint('coffee', __name__)

# ==============================================
# ROUTES FOR SALES MANAGEMENT
# ==============================================

@bp.route('/')
@login_required
def list_sales():
    # Get filter parameters
    search_query = request.args.get('q', '')
    category = request.args.get('category')
    sort = request.args.get('sort', 'date_desc')
    
    # Base query
    query = CoffeeSale.query.join(Product)
    
    # Apply filters
    if search_query:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search_query}%'),
                Product.description.ilike(f'%{search_query}%')
            )
        )
    
    if category:
        query = query.filter(Product.category == category)
    
    # Apply sorting
    if sort == 'date_asc':
        query = query.order_by(CoffeeSale.date.asc())
    elif sort == 'amount_desc':
        query = query.order_by(CoffeeSale.total_sales.desc())
    elif sort == 'amount_asc':
        query = query.order_by(CoffeeSale.total_sales.asc())
    else:  # Default: date_desc
        query = query.order_by(CoffeeSale.date.desc())
    
    # Get unique categories for filter dropdown
    categories = db.session.query(Product.category.distinct()).order_by(Product.category).all()
    categories = [c[0] for c in categories]
    
    sales = query.all()
    return render_template('coffee/list.html', sales=sales, categories=categories)
@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_sale():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = float(request.form.get('quantity'))
        unit_price = float(request.form.get('unit_price'))
        payment_mode = request.form.get('payment_mode')
        waiter_id_raw = request.form.get('waiter_id')
        
        try:
            waiter_id = int(waiter_id_raw) if waiter_id_raw else None
        except (TypeError, ValueError):
            waiter_id = None

        product = Product.query.get_or_404(product_id)

        if product.current_stock < quantity:
            flash(f'Not enough stock available. Only {product.current_stock} {product.unit} left', 'danger')
            return redirect(url_for('coffee.new_sale'))

        total_sales = quantity * unit_price

        # Automatically determine current shift based on time
        now = datetime.now(pytz.timezone('Africa/Kigali')).time()
        day_shift_start = datetime.strptime('07:00', '%H:%M').time()
        night_shift_start = datetime.strptime('17:00', '%H:%M').time()
        current_shift = None

        if day_shift_start <= now < night_shift_start:
            current_shift = Shift.query.filter(
                (Shift.name == 'Day Shift') | (Shift.name == 'Day Shift'),
                Shift.is_active == True
            ).first()
            if not current_shift:
                current_shift = Shift.query.filter_by(name='Day Shift', is_active=True).first()
        else:
            current_shift = Shift.query.filter(
                (Shift.name == 'Night Shift') | (Shift.name == 'Night Shift'),
                Shift.is_active == True
            ).first()
            if not current_shift:
                current_shift = Shift.query.filter_by(name='Night Shift', is_active=True).first()

        sale = CoffeeSale(
            product_id=product.id,
            quantity_sold=quantity,
            unit_price=unit_price,
            total_sales=total_sales,
            payment_mode=payment_mode,
            recorded_by=current_user.id,
            waiter_id=waiter_id,
            shift_id=current_shift.id
        )

        product.current_stock -= quantity
        db.session.add(sale)
        db.session.commit()

        flash('Sale recorded successfully', 'success')
        return redirect(url_for('coffee.list_sales'))

    # GET request handling
    products = Product.query.order_by(Product.name).all()
    waiters = Waiter.query.filter_by(is_active=True).order_by(Waiter.name).all()
    return render_template('coffee/form.html', products=products, waiters=waiters)

# ==============================================
# REPORTING ROUTES
# ==============================================

@bp.route('/report')
@login_required
def sales_report():
    # Aggregate sales by product
    sales_by_product = (
        db.session.query(
            Product.name.label('name'),
            func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
            func.sum(CoffeeSale.total_sales).label('total_sales'),
        )
        .join(CoffeeSale, CoffeeSale.product_id == Product.id)
        .group_by(Product.name)
        .order_by(func.sum(CoffeeSale.total_sales).desc())
        .all()
    )
    
    # Aggregate sales by payment mode
    sales_by_payment = (
        db.session.query(
            CoffeeSale.payment_mode.label('payment_mode'),
            func.sum(CoffeeSale.total_sales).label('total_sales'),
        )
        .group_by(CoffeeSale.payment_mode)
        .all()
    )
    
    # Most recent 10 sales
    recent_sales = CoffeeSale.query.order_by(CoffeeSale.date.desc()).limit(10).all()
    waiters = Waiter.query.filter_by(is_active=True).all()
    
    return render_template(
        'coffee/report.html',
        sales_by_product=sales_by_product,
        sales_by_payment=sales_by_payment,
        recent_sales=recent_sales,
        currency='Rwf',
        waiters=waiters
    )

@bp.route('/general_report')
@login_required
def general_report():
    # Date filter from query param
    selected_date_str = request.args.get('date')
    selected_category = request.args.get('category')  # New category filter
    selected_date = None
    
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = None

    # Base queries
    coffee_sales_query = CoffeeSale.query.join(Product)
    orders_query = Order.query

    # Apply filters
    if selected_date:
        start = datetime.combine(selected_date, datetime.min.time())
        end = datetime.combine(selected_date, datetime.max.time())
        coffee_sales_query = coffee_sales_query.filter(
            CoffeeSale.date >= start, CoffeeSale.date <= end
        )
        orders_query = orders_query.filter(
            Order.date >= start, Order.date <= end
        )

    if selected_category:
        coffee_sales_query = coffee_sales_query.filter(Product.category == selected_category)
        # For orders, we need to join through order items to products
        orders_query = orders_query.join(Order.items).join(Product).filter(Product.category == selected_category)

    # Get unique categories for filter dropdown
    categories = db.session.query(Product.category.distinct()).order_by(Product.category).all()
    categories = [c[0] for c in categories]

    # Execute queries
    coffee_sales = coffee_sales_query.order_by(CoffeeSale.date.desc()).all()
    orders = orders_query.order_by(Order.date.desc()).all()

    # Aggregate totals
    total_coffee_sales = sum(s.total_sales for s in coffee_sales)
    total_order_sales = sum(o.total_amount for o in orders)
    grand_total = total_coffee_sales + total_order_sales

    # Prepare recent transactions
    recent_transactions = [
        {
            'type': 'Coffee Sale',
            'date': s.date,
            'product': s.product.name,
            'waiter': s.waiter.name if s.waiter else None,
            'shift': s.shift,
            'qty': s.quantity_sold,
            'unit_price': s.unit_price,
            'total': s.total_sales,
            'payment': s.payment_mode
        }
        for s in coffee_sales
    ] + [
        {
            'type': 'Order',
            'date': o.date,
            'product': ', '.join([item.product.name for item in o.items]),
            'waiter': o.waiter.name if o.waiter else None,
            'shift': o.shift,
            'qty': sum(item.quantity for item in o.items),
            'unit_price': '',
            'total': o.total_amount,
            'payment': o.payment_method if hasattr(o, 'payment_method') else 'N/A'  # Updated this line
        }
        for o in orders
    ]

    recent_transactions.sort(key=lambda x: x['date'], reverse=True)

    return render_template(
        'general_report.html',
        total_coffee_sales=total_coffee_sales,
        total_order_sales=total_order_sales,
        grand_total=grand_total,
        recent_transactions=recent_transactions,
        currency='Rwf',
        selected_date=selected_date_str or '',
        categories=categories,  # Pass categories to template
        selected_category=selected_category  # Pass selected category to template
    )
# ==============================================
# EXPORT ROUTES
# ==============================================

@bp.route('/report/excel')
@login_required
def export_excel():
    # Get sales data
    sales_by_product = db.session.query(
        Product.name,
        func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).group_by(Product.name).order_by(func.sum(CoffeeSale.total_sales).desc()).all()
    
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).group_by(CoffeeSale.payment_mode).all()
    
    # Create DataFrames
    product_df = pd.DataFrame(sales_by_product, columns=['Product', 'Quantity Sold', 'Total Sales'])
    payment_df = pd.DataFrame(sales_by_payment, columns=['Payment Mode', 'Total Sales'])
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        product_df.to_excel(writer, sheet_name='Sales by Product', index=False)
        payment_df.to_excel(writer, sheet_name='Sales by Payment', index=False)
        
        # Formatting
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        # Apply formatting
        for sheet_name in ['Sales by Product', 'Sales by Payment']:
            worksheet = writer.sheets[sheet_name]
            df = product_df if sheet_name == 'Sales by Product' else payment_df
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                max_len = max(df[value].astype(str).map(len).max(), len(value)) + 2
                worksheet.set_column(col_num, col_num, max_len)
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=coffee_sales_report.xlsx'
    return response

@bp.route('/report/pdf')
@login_required
def export_pdf():
    # Get sales data
    sales_by_product = db.session.query(
        Product.name,
        func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).group_by(Product.name).order_by(func.sum(CoffeeSale.total_sales).desc()).all()
    
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).group_by(CoffeeSale.payment_mode).all()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title and timestamp
    elements.append(Paragraph("Coffee Sales Report", styles['Title']))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))
    
    # Sales by Product table
    elements.append(Paragraph("Sales by Product", styles['Heading2']))
    product_data = [['Product', 'Quantity Sold', 'Total Sales']]
    for product in sales_by_product:
        product_data.append([product.name, f"{product.total_quantity:.2f}", f"Rwf {product.total_sales:.2f}"])
    
    product_table = Table(product_data)
    product_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(product_table)
    elements.append(Paragraph(" ", styles['Normal']))
    
    # Sales by Payment table
    elements.append(Paragraph("Sales by Payment Method", styles['Heading2']))
    payment_data = [['Payment Method', 'Total Sales']]
    for payment in sales_by_payment:
        payment_data.append([payment.payment_mode, f"Rwf {payment.total_sales:.2f}"])
    
    payment_table = Table(payment_data)
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(payment_table)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=coffee_sales_report.pdf'
    return response

@bp.route('/transactions/excel')
@login_required
def export_transactions_excel():
    """Export recent stock movements as an Excel file"""
    movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(50).all()

    # Build DataFrame
    data = []
    for m in movements:
        data.append({
            'Date': m.date.strftime('%Y-%m-%d %H:%M'),
            'Product': m.product.name if m.product else 'N/A',
            'Opening Stock': m.opening_stock,
            'Stock In': m.stock_in,
            'Stock Out': m.stock_out,
            'Closing Stock': m.closing_stock,
            'Movement Type': m.movement_type,
            'User': m.user.username if m.user else 'N/A',
            'Notes': m.notes or ''
        })
    
    df = pd.DataFrame(data)

    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Recent Transactions')
        
        # Formatting
        workbook = writer.book
        worksheet = writer.sheets['Recent Transactions']
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })

        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            col_width = max(df[value].astype(str).map(len).max(), len(value)) + 2
            worksheet.set_column(col_num, col_num, col_width)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="recent_transactions.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@bp.route('/download/pdf')
@login_required
def export_transactions_pdf():
    """Download product list as a PDF file"""
    products = Product.query.order_by(Product.name).all()

    html = render_template_string("""
    <html>
    <head><style>table, th, td { border: 1px solid black; border-collapse: collapse; padding: 5px; }</style></head>
    <body>
    <h2>Product List</h2>
    <table>
        <thead>
            <tr>
                <th>SKU</th><th>Name</th><th>Category</th><th>Brand</th>
                <th>Description</th><th>Unit</th><th>Current Stock</th>
                <th>Min Stock</th><th>Reorder Qty</th><th>Cost Price</th>
                <th>Unit Price</th><th>Tax Rate</th>
            </tr>
        </thead>
        <tbody>
        {% for p in products %}
            <tr>
                <td>{{ p.sku }}</td><td>{{ p.name }}</td><td>{{ p.category }}</td><td>{{ p.brand or '' }}</td>
                <td>{{ p.description or '' }}</td><td>{{ p.unit }}</td><td>{{ p.current_stock }}</td>
                <td>{{ p.min_stock }}</td><td>{{ p.reorder_qty }}</td><td>{{ p.cost_price }}</td>
                <td>{{ p.unit_price }}</td><td>{{ p.tax_rate }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    </body>
    </html>
    """, products=products)

    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)

    if pisa_status.err:
        flash("Error generating PDF", "danger")
        return redirect(url_for('product.list_products'))

    result.seek(0)
    return send_file(result, as_attachment=True, download_name="product_list.pdf", mimetype='application/pdf')

# ==============================================
# DASHBOARD AND UTILITY ROUTES
# ==============================================

@bp.route('/dashboard')
@login_required
def dashboard():
    selected_date_str = request.args.get('selected_date')

    if selected_date_str:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
        start = datetime.combine(selected_date.date(), datetime.min.time())
        end = datetime.combine(selected_date.date(), datetime.max.time())

        movements = StockMovement.query.filter(
            StockMovement.date >= start,
            StockMovement.date <= end
        ).all()
    else:
        movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(50).all()

    return render_template('dashboard.html', movements=movements, now=datetime.utcnow())

@bp.route('/get_todays_revenue')
@login_required
def get_todays_revenue():
    try:
        today = datetime.utcnow().date()
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        
        total = db.session.query(func.sum(CoffeeSale.total_sales))\
                 .filter(CoffeeSale.date.between(start, end))\
                 .scalar() or 0
                 
        return jsonify({
            'status': 'success',
            'revenue': float(total),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500