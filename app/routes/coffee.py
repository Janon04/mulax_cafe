from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response
from flask_login import login_required, current_user
from app.models import CoffeeSale, Product, StockMovement
from flask import jsonify
from app import db
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from openpyxl import Workbook
from flask import send_file
from io import BytesIO
from xhtml2pdf import pisa
from sqlalchemy import func
from flask import make_response, render_template_string

bp = Blueprint('coffee', __name__)

@bp.route('/')
@login_required
def list_sales():
    sales = CoffeeSale.query.order_by(CoffeeSale.date.desc()).all()
    return render_template('coffee/list.html', sales=sales)

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_sale():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = float(request.form.get('quantity'))
        unit_price = float(request.form.get('unit_price'))
        payment_mode = request.form.get('payment_mode')
        
        product = Product.query.get_or_404(product_id)
        
        if product.current_stock < quantity:
            flash(f'Not enough stock available. Only {product.current_stock} {product.unit} left', 'danger')
            return redirect(url_for('coffee.new_sale'))
        
        total_sales = quantity * unit_price
        
        sale = CoffeeSale(
            product_id=product.id,
            quantity_sold=quantity,
            unit_price=unit_price,
            total_sales=total_sales,
            payment_mode=payment_mode,
            recorded_by=current_user.id
        )
        
        product.current_stock -= quantity
        
        db.session.add(sale)
        db.session.commit()
        
        flash('Sale recorded successfully', 'success')
        return redirect(url_for('coffee.list_sales'))
    
    products = Product.query.order_by(Product.name).all()
    return render_template('coffee/form.html', products=products)
@bp.route('/report')
@login_required
def sales_report():
    # Aggregate sales by product
    sales_by_product = (
        db.session.query(
            Product.name.label('name'),
            db.func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
            db.func.sum(CoffeeSale.total_sales).label('total_sales'),
        )
        .join(CoffeeSale, CoffeeSale.product_id == Product.id)
        .group_by(Product.name)
        .order_by(db.func.sum(CoffeeSale.total_sales).desc())
        .all()
    )
    
    # Aggregate sales by payment mode
    sales_by_payment = (
        db.session.query(
            CoffeeSale.payment_mode.label('payment_mode'),
            db.func.sum(CoffeeSale.total_sales).label('total_sales'),
        )
        .group_by(CoffeeSale.payment_mode)
        .all()
    )
    
    # Most recent 10 sales
    recent_sales = (
        CoffeeSale.query
        .order_by(CoffeeSale.date.desc())
        .limit(10)
        .all()
    )
    
    return render_template(
        'coffee/report.html',
        sales_by_product=sales_by_product,
        sales_by_payment=sales_by_payment,
        recent_sales=recent_sales,
        currency='Rwf'
    )


bp.route('/report/excel')
@login_required
def export_excel():
    # Get sales data
    sales_by_product = db.session.query(
        Product.name,
        db.func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        db.func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).group_by(Product.name).order_by(db.func.sum(CoffeeSale.total_sales).desc()).all()
    
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        db.func.sum(CoffeeSale.total_sales).label('total_sales')
    ).group_by(CoffeeSale.payment_mode).all()
    
    # Create DataFrames
    product_df = pd.DataFrame(sales_by_product, columns=['Product', 'Quantity Sold', 'Total Sales'])
    payment_df = pd.DataFrame(sales_by_payment, columns=['Payment Mode', 'Total Sales'])
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Sales by Product sheet
        product_df.to_excel(writer, sheet_name='Sales by Product', index=False)
        
        # Sales by Payment sheet
        payment_df.to_excel(writer, sheet_name='Sales by Payment', index=False)
        
        # Get workbook and worksheet objects for formatting
        workbook = writer.book
        product_sheet = writer.sheets['Sales by Product']
        payment_sheet = writer.sheets['Sales by Payment']
        
        # Format headers
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        # Apply header format
        for col_num, value in enumerate(product_df.columns.values):
            product_sheet.write(0, col_num, value, header_format)
        
        for col_num, value in enumerate(payment_df.columns.values):
            payment_sheet.write(0, col_num, value, header_format)
        
        # Auto-adjust column widths

        for i, col in enumerate(product_df.columns):
            max_len = max(
                product_df[col].astype(str).map(len).max(),
                len(str(col))
            )
            product_sheet.set_column(i, i, max_len + 2)

        for i, col in enumerate(payment_df.columns):
            max_len = max(
                payment_df[col].astype(str).map(len).max(),
                len(str(col))
            )
            payment_sheet.set_column(i, i, max_len + 2)
    
    output.seek(0)
    
    # Create response
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
        db.func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        db.func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).group_by(Product.name).order_by(db.func.sum(CoffeeSale.total_sales).desc()).all()
    
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        db.func.sum(CoffeeSale.total_sales).label('total_sales')
    ).group_by(CoffeeSale.payment_mode).all()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    
    # Styles
    styles = getSampleStyleSheet()
    
    # Content
    elements = []
    
    # Title
    elements.append(Paragraph("Coffee Sales Report", styles['Title']))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))  # Spacer
    
    # Sales by Product table
    elements.append(Paragraph("Sales by Product", styles['Heading2']))
    product_data = [['Product', 'Quantity Sold', 'Total Sales']]
    for product in sales_by_product:
        product_data.append([
            product.name,
            f"{product.total_quantity:.2f}",
            f"${product.total_sales:.2f}"
        ])
    
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
    elements.append(Paragraph(" ", styles['Normal']))  # Spacer
    
    # Sales by Payment table
    elements.append(Paragraph("Sales by Payment Method", styles['Heading2']))
    payment_data = [['Payment Method', 'Total Sales']]
    for payment in sales_by_payment:
        payment_data.append([
            payment.payment_mode,
            f"${payment.total_sales:.2f}"
        ])
    
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
    
    # Build PDF
    doc.build(elements)
    
    buffer.seek(0)
    
    # Create response
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=coffee_sales_report.pdf'
    return response

@bp.route('/dashboard')
@login_required
def dashboard():
    selected_date_str = request.args.get('selected_date')

    if selected_date_str:
        # Parse selected date
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
        # Create start and end range for that day
        start = datetime.combine(selected_date.date(), datetime.min.time())
        end = datetime.combine(selected_date.date(), datetime.max.time())

        # Filter stock movements for that day
        movements = StockMovement.query.filter(
            StockMovement.date >= start,
            StockMovement.date <= end
        ).all()
    else:
        movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(50).all()

    return render_template('dashboard.html', movements=movements, now=datetime.utcnow())

@bp.route('/transactions/excel')
@login_required
def export_transactions_excel():
    """Export recent stock movements as an Excel file"""
    # Fetch recent 50 stock movements
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

    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Recent Transactions')

        # Format headers
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
@bp.route('/download/pdf', methods=['GET'])
@login_required
def export_transactions_pdf():
    """Download product list as a PDF file"""
    products = Product.query.order_by(Product.name).all()

    # Simple HTML table (you can replace with a real template if you like)
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

    # Generate PDF
    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)

    if pisa_status.err:
        flash("Error generating PDF", "danger")
        return redirect(url_for('product.list_products'))

    result.seek(0)
    return send_file(result, as_attachment=True, download_name="product_list.pdf", mimetype='application/pdf')

# ..................................
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