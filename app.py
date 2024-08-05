from flask import Flask, render_template, request, redirect, url_for, session
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use a non-GUI backend for rendering plots in Flask
import matplotlib.pyplot as plt
import io
import base64
import os

# Initialize the Flask application
app = Flask(__name__)

# Set a secret key for session management
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# Define a route
@app.route('/')
def home():
    return "Hello, Heroku!"  # Simple test to ensure routing works

# Main entry point for running the app locally
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use the port provided by Heroku
    app.run(host='0.0.0.0', port=port)

# Main entry point for running the app locally
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use the port provided by Heroku
    app.run(host='0.0.0.0', port=port)



@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Get user inputs from the form
        portfolio_amount = float(request.form['portfolio_amount'])
        avg_annual_return = float(request.form['avg_annual_return']) / 100
        volatility = float(request.form['volatility']) / 100
        inflation_choice = request.form['inflation']
        time_horizon = int(request.form['time_horizon'])

        # Set inflation rate based on user choice
        if inflation_choice == 'random':
            base_inflation_rate = np.random.uniform(0.01, 0.15)
        else:
            base_inflation_rate = float(inflation_choice) / 100

        # Initialize session variables
        session['starting_portfolio'] = portfolio_amount
        session['portfolio_amount'] = portfolio_amount
        session['avg_annual_return'] = avg_annual_return
        session['volatility'] = volatility
        session['base_inflation_rate'] = base_inflation_rate
        session['time_horizon'] = time_horizon
        session['target_withdrawal'] = 0.05 * portfolio_amount  # 5% initial withdrawal
        session['total_withdrawn'] = 0
        session['year'] = 0
        session['portfolio_values'] = [portfolio_amount]
        session['withdrawals'] = []
        session['inflations'] = []

        # Redirect to the yearly simulation page
        return redirect(url_for('yearly_simulation'))
    
    return render_template('index.html')

@app.route('/yearly', methods=['GET', 'POST'])
def yearly_simulation():
    # Retrieve session data
    portfolio_amount = session['portfolio_amount']
    target_withdrawal = session['target_withdrawal']
    year = session['year']
    total_withdrawn = session['total_withdrawn']

    if request.method == 'POST':
        withdrawal = float(request.form['withdrawal'])
        margin_percent = float(request.form['margin_percent']) / 100

        # Update session data with user inputs
        portfolio_amount -= withdrawal
        total_withdrawn += withdrawal
        session['withdrawals'].append(withdrawal)

        # Check if portfolio is depleted
        if portfolio_amount <= 0:
            return redirect(url_for('game_over', message="Your portfolio has been depleted. Game over!"))

        # Calculate the annual return and inflation
        annual_return = np.random.normal(session['avg_annual_return'], session['volatility'])
        inflation_rate = np.random.normal(session['base_inflation_rate'], 0.005)

        # Cap extreme inflation values
        inflation_rate = max(-0.01, min(inflation_rate, 0.10))

        # Update inflation list
        session['inflations'].append(inflation_rate)

        # Update target withdrawal for the next year
        target_withdrawal *= (1 + inflation_rate)
        session['target_withdrawal'] = target_withdrawal

        # Update portfolio for margin
        effective_return = annual_return * (1 + margin_percent)
        new_portfolio_value = portfolio_amount * (1 + effective_return)

        # Check for margin call
        margined_value = portfolio_amount * (1 + margin_percent)
        if new_portfolio_value < margined_value * 0.25:
            return redirect(url_for('game_over', message="Margin call! Your portfolio has been liquidated. Game over!"))

        # Update portfolio and session data
        session['portfolio_amount'] = new_portfolio_value
        session['portfolio_values'].append(new_portfolio_value)

        # Increment the year counter after processing the current year
        session['year'] += 1

        # Check if the time horizon has been reached
        if session['year'] >= session['time_horizon']:
            # End of simulation
            return redirect(url_for('results'))

    # Render the yearly simulation page with current values
    return render_template('yearly.html', data={
        'year': year + 1,  # Incrementing year for display
        'portfolio_amount': portfolio_amount,
        'target_withdrawal': target_withdrawal,
        'value_on_margin': portfolio_amount * 0.5,  # Example calculation
        'total_withdrawn': total_withdrawn
    })

@app.route('/results')
def results():
    # Retrieve session data
    ending_portfolio = session['portfolio_amount']
    starting_portfolio = session['starting_portfolio']
    years_played = session['year']
    
    # Calculate expected and actual withdrawals
    total_expected_withdrawals = starting_portfolio * 0.05 * years_played  # Expected 5% withdrawal rate each year
    total_actual_withdrawals = sum(session['withdrawals'])

    # Determine if a margin call occurred
    margin_call = any(portfolio_value < 0 for portfolio_value in session['portfolio_values'])

    # Calculate the final score
    score = calculate_final_score(
        starting_portfolio,
        ending_portfolio,
        total_expected_withdrawals,
        total_actual_withdrawals,
        margin_call
    )

    # Prepare results dictionary
    results = {
        'Beginning Portfolio Value': f"${starting_portfolio:,.2f}",
        'Ending Portfolio Value': f"${ending_portfolio:,.2f}",
        'Total Actual Withdrawals': f"${total_actual_withdrawals:,.2f}",
        'Total Expected Withdrawals': f"${total_expected_withdrawals:,.2f}",
        'Final Score': f"{score:.2f}/100"
    }

    # Generate Plot
    plot_url = generate_plot(session['portfolio_values'], years_played)

    # Render the results page
    return render_template('results.html', results=results, plot_url=plot_url)

@app.route('/game_over')
def game_over():
    # Retrieve the message to be displayed
    message = request.args.get('message', 'Game over!')
    return render_template('game_over.html', message=message)

def generate_plot(portfolio_values, years_played):
    plt.figure(figsize=(10, 6))
    plt.plot(range(years_played + 1), portfolio_values, marker='o')
    plt.title("Portfolio Value Over Time")
    plt.xlabel("Year")
    plt.ylabel("Portfolio Value ($)")
    plt.grid(True)

    # Save plot to a PNG image in memory
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    # Close the plot to free memory
    plt.close()

    return f"data:image/png;base64,{plot_url}"


def calculate_final_score(starting_portfolio, ending_portfolio, total_expected_withdrawals, total_actual_withdrawals, margin_call=False):
    # Base score of 1 if the game ends in failure (margin call or depletion)
    if margin_call or ending_portfolio <= 0:
        return 1

    # Calculate the return on the portfolio
    actual_return = (ending_portfolio - starting_portfolio + total_actual_withdrawals) / starting_portfolio

    # Calculate the expected portfolio growth without withdrawals
    expected_return = (total_expected_withdrawals + starting_portfolio) / starting_portfolio

    # Calculate withdrawal performance ratio
    withdrawal_ratio = total_actual_withdrawals / total_expected_withdrawals

    # Score calculation
    # Base score starts at 50 for meeting expected conditions
    base_score = 50

    # Adjust based on how much actual withdrawals exceed expected withdrawals
    if withdrawal_ratio > 1:
        # Withdrawals exceeded expectations, increase score
        score = base_score + 50 * (withdrawal_ratio - 1)
    else:
        # Withdrawals were less than expected, decrease score
        score = base_score * withdrawal_ratio

    # Further adjust score based on actual vs expected returns
    if actual_return > expected_return:
        score += 10 * (actual_return - expected_return)
    else:
        score -= 10 * (expected_return - actual_return)

    # Normalize score to be between 1 and 100
    score = max(1, min(100, score))

    return score

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

import os

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
