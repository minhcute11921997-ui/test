```python
from flask import Flask, render_template, request, redirect, url_for

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

@app.route('/update/<int:product_id>', methods=['GET', 'POST'])
def update_product(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return "Product not found", 404

    if request.method == 'POST':
        product['name'] = request.form['name']
        product['price'] = float(request.form['price'])
        return redirect(url_for('index'))

    return render_template('update_product.html', product=product)

if __name__ == '__main__':
    app.run(debug=True)
```