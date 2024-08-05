from flask import Flask, render_template, request
import numpy as np
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Get user inputs
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

        # Run Monte Carlo Simulation
        results, plot_url = monte_carlo_simulation(portfolio_amount, avg_annual_return, volatility, base_inflation_rate, time_horizon)

        # Display results
        return render_template('results.html', results=results, plot_url=plot_url)
    
    return render_template('index.html')

def monte_carlo_simulation(portfolio_amount, avg_annual_return, volatility, base_inflation_rate, time_horizon):
    # Fixed Variables
    target_withdrawal_rate = 0.05  # Initial target withdrawal is 5% of the initial portfolio
    avg_inflation_volatility = 0.005  # Adjusted volatility to reflect realistic inflation
    regt_margin_limit = 0.50  # Max 50% of the portfolio can be margined
    margin_call_threshold = 0.25  # If portfolio drops below 25% of its margined value, a margin call occurs

    # Initialize Portfolio
    starting_portfolio = portfolio_amount
    portfolio_values = [portfolio_amount]
    withdrawals = []
    inflations = []
    total_withdrawn = 0
    years_played = 0

    for year in range(1, time_horizon + 1):
        # Determine the annual return and inflation
        annual_return = np.random.normal(avg_annual_return, volatility)
        inflation_rate = np.random.normal(base_inflation_rate, avg_inflation_volatility)

        # Cap extreme inflation values
        inflation_rate = max(-0.01, min(inflation_rate, 0.10))

        # Update Inflation List
        inflations.append(inflation_rate)

        # Calculate Target Withdrawal based on initial portfolio amount
        if year == 1:
            # Target withdrawal at year 1 is 5% of initial portfolio
            target_withdrawal = target_withdrawal_rate * starting_portfolio
        else:
            # In subsequent years, adjust target withdrawal for inflation
            target_withdrawal = target_withdrawal * (1 + inflation_rate)

        # Example: Fixed withdrawal for simplicity
        withdrawal = target_withdrawal
        margin_percent = 0.20  # Example fixed margin percent

        # Update Portfolio for Withdrawal
        portfolio_values[-1] -= withdrawal
        total_withdrawn += withdrawal
        withdrawals.append(withdrawal)

        # Check if Portfolio is Depleted
        if portfolio_values[-1] <= 0:
            break

        # Update Portfolio for Margin
        effective_return = annual_return * (1 + margin_percent)
        new_portfolio_value = portfolio_values[-1] * (1 + effective_return)
        
        # Check for Margin Call
        margined_value = portfolio_values[-1] * (1 + margin_percent)
        if new_portfolio_value < margined_value * margin_call_threshold:
            break

        portfolio_values.append(new_portfolio_value)
        years_played += 1

    # Adjust total withdrawn to exclude the last two withdrawals
    if len(withdrawals) >= 2:
        adjusted_total_withdrawn = sum(withdrawals[:-2])
    else:
        adjusted_total_withdrawn = sum(withdrawals)
    
    # End Game Summary
    ending_portfolio = portfolio_values[-1]
    total_returns_excluding_withdrawals = ending_portfolio - starting_portfolio
    total_returns_including_withdrawals = ending_portfolio + total_withdrawn - starting_portfolio
    adjusted_total_returns_including_withdrawals = ending_portfolio + adjusted_total_withdrawn - starting_portfolio
    cagr = (ending_portfolio / starting_portfolio) ** (1 / years_played) - 1 if ending_portfolio > 0 else -1
    avg_withdrawn_per_year = adjusted_total_withdrawn / years_played if years_played > 0 else 0

    # Prepare results dictionary
    results = {
        'Beginning Portfolio Value': f"${starting_portfolio:,.2f}",
        'Ending Portfolio Value': f"${ending_portfolio:,.2f}",
        'Total Returns (excluding withdrawals)': f"${total_returns_excluding_withdrawals:,.2f}",
        'Total Returns (including withdrawals)': f"${total_returns_including_withdrawals:,.2f}",
        'Adjusted Total Returns (excluding last two withdrawals)': f"${adjusted_total_returns_including_withdrawals:,.2f}",
        'CAGR (including withdrawals)': f"{cagr * 100:.2f}%",
        'Average Amount Withdrawn Per Year (excluding last two withdrawals)': f"${avg_withdrawn_per_year:,.2f}"
    }

    # Generate Plot
    plot_url = generate_plot(portfolio_values, years_played)

    return results, plot_url

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

if __name__ == '__main__':
    app.run(debug=True)
