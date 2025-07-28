# ☕ Mulax Café – Flask Management System

**Mulax Café** is a Flask-based management application designed to streamline day-to-day café operations. It provides powerful tools for managing sales, requisitions, stock levels, user roles, order flows, and more.

---

## 📦 Features

- 🔐 User Authentication with Role-Based Access (Admin, Manager, Employee)
- 📋 Requisition & Approval Workflow with Status Tracking
- 📊 Sales Reporting by Product & Payment Type
- ☕ Order Management (Tables, Items, Server Tracking)
- 📦 Stock Movement Tracking (In/Out with Auto Calculations)
- 🛠️ Flask-Admin Integration for Backend Views
- 📱 API Ready with Flask-RESTx
- ✉️ Notification Logging (Email/SMS)

---

## 🧱 Technologies Used

- Flask & Flask-Login
- Flask-SQLAlchemy
- Flask-Admin
- Flask-Migrate
- Flask-RESTx
- Bootstrap 5 (HTML Templates)
- SQLite / PostgreSQL / MySQL Compatible

---

## 🧪 Models Overview

The system includes the following major data models:

| Model          | Description |
|----------------|-------------|
| `User`         | Manages system users and roles |
| `Product`      | Tracks stock, categories, units, and pricing |
| `Requisition`  | Handles internal item requests with approvals |
| `CoffeeSale`   | Logs individual product sales with payment mode |
| `Order`        | Full order lifecycle: recorded, served, completed |
| `OrderItem`    | Items associated with orders |
| `Client`       | Customer details for tracked orders |
| `Table`        | Café table tracking with capacity and location |
| `StockMovement`| Logs all stock in/out activities |
| `NotificationLog` | Logs for email/SMS communication attempts |

---

## 🚀 Getting Started

To run this project locally:

```bash
# 1. Clone the repository
git clone https://github.com/Janon04/mulax_cafe.git
cd mulax_cafe

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables (if needed)
export FLASK_APP=run.py
export FLASK_ENV=development

# 5. Run database migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# 6. Run the app
python run.py
