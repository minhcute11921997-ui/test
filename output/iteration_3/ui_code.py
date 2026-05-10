```python
from flask import Flask, render_template

app = Flask(__name__)

# Sample data for products
products = [
    {'id': 1, 'name': 'Product A', 'price': 10.99},
    {'id': 2, 'name': 'Product B', 'price': 15.99},
    {'id': 3, 'name': 'Product C', 'price': 20.99}
]

@app.route('/')
def index():
    return render_template('products.html', products=products)

if __name__ == '__main__':
    app.run(debug=True)
```

```html
<!-- templates/products.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Product List</title>
    <style>
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
        }
        th {
            background-color: #f2f2f2;
        }
    </style>
</head>
<body>
    <h1>Product List</h1>
    <table>
        <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Price</th>
        </tr>
        {% for product in products %}
        <tr>
            <td>{{ product.id }}</td>
            <td>{{ product.name }}</td>
            <td>${{ product.price }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
```