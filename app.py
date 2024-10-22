import os

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# current date of the transaction
date = datetime.now().date()



@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # get the user id.
    id = session["user_id"]

    # retrive username.
    user_name = db.execute("SELECT username FROM users WHERE id= ?", id)

    if not user_name:
        return apology("User not found", 404)

    username = user_name[0]["username"]

    # retrieve stocks of the user.
    stocks = db.execute("SELECT * FROM stocks WHERE user_id= ?", id)

    # retrieve cash balance of the user.
    cash = db.execute("SELECT cash FROM users WHERE id= ?", id)
    cash_balance = cash[0]["cash"]

    # define that is an int
    total_shares_cost = 0

    # retrieve shares and current value of the stocks to obtain the grand_total.
    for stock in stocks:
        live_stock = lookup(stock["stock_symbol"])
        shares = stock["shares"]
        total_share_cost = int(shares) * live_stock["price"]
        total_shares_cost = total_shares_cost + (int(shares) * float(live_stock["price"]))

        if not db.execute("SELECT * FROM stocks_index WHERE user_id = ? AND stock_symbol = ?", id, stock["stock_symbol"]):
            db.execute("INSERT INTO stocks_index (user_id, username, stock_symbol, shares, current_price, total_value) VALUES (?, ?, ?, ?, ?, ?)", id, username, stock["stock_symbol"], stock["shares"], (live_stock["price"]), round(total_share_cost, 2))
        else:
            db.execute("UPDATE stocks_index SET shares= ?, current_price= ?, total_value= ? WHERE user_id= ? AND stock_symbol= ?", shares, (live_stock["price"]), round(total_share_cost, 2), id, stock["stock_symbol"])


    stocks_index = db.execute("SELECT * FROM stocks_index WHERE user_id= ?", session["user_id"])

    # grand total is cash + shares total value
    grand_total = cash_balance + round(total_shares_cost, 2)

    # update or create if not created a table of the grand total and cash balance of the user.
    if not db.execute("SELECT * FROM balance WHERE user_id= ?", id):
        db.execute("INSERT INTO balance (user_id, cash_balance, grand_total) VALUES (?, ?, ?)", id, round(cash_balance, 2), grand_total)
    else:
        db.execute("UPDATE balance SET cash_balance= ?, grand_total= ? WHERE user_id= ?", round(cash_balance, 2), grand_total, id)
    # store the balance table in a variable
    balance = db.execute("SELECT * FROM balance WHERE user_id= ?", id)


    return render_template("index.html", username=username, balance=balance, stocks=stocks_index)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # if the form is submitted.
    if request.method == "POST":

        # if the user does not enter a symbol or is not an actual symbol in the API
        if not request.form.get("symbol") or not lookup(request.form.get("symbol")):
            return apology("stock not inputted/stock does not exist", 400)

        # if the user does not enter a symbol or the shares is less or equal to 0
        elif not request.form.get("shares") or int(request.form.get("shares")) <= 0:
            return apology("must input shares amount", 400)

        # shares into an integer
        shares = int(request.form.get("shares"))

        # the API of the stock
        stock = lookup(request.form.get("symbol"))

        id = session["user_id"]


        # the return value of the db.execute is a list of dict.
        result = db.execute("SELECT cash FROM users WHERE id = ?", id)

        # the first row and the key cash will be the result of the cash in str
        cash = result[0]["cash"]

        # total cost of the transaction
        total_cost = shares * round(stock["price"], 2)

        # validate if the price of the shares exceeds the cash of the user.
        if int(cash) < total_cost:
            return apology("not enough money", 400)


        # update the cash of the user after validating that can afford the price.
        newcash = round(cash, 2) - (shares * round(stock["price"], 2))
        db.execute("UPDATE users SET cash= ? WHERE id= ?", newcash, id)


        # update the history table on that user.
        db.execute("INSERT INTO history (user_id, transaction_type, stock, shares, share_price, total_cost, date) VALUES (?, ?, ?, ?, ?, ?, ?)", id, "buy", stock["symbol"], shares, round(stock["price"], 2), total_cost, date)

        # update the stocks table on that user.
        if not db.execute("SELECT * FROM stocks WHERE user_id = ? AND stock_symbol = ?", id, stock["symbol"]):
            user_name = db.execute("SELECT username FROM users WHERE id= ?", id)
            username = user_name[0]["username"]
            db.execute("INSERT INTO stocks (user_id, username, stock_symbol, shares) VALUES (?, ?, ?, ?)", id, username, stock["symbol"], shares)
        else:
            # add the shares
            previous_shares = db.execute("SELECT shares FROM stocks WHERE user_id = ? AND stock_symbol = ?", id, stock["symbol"])
            total_shares = shares + int(previous_shares[0]["shares"])
            db.execute("UPDATE stocks SET shares = ? WHERE user_id = ? AND stock_symbol = ?", total_shares, id, stock["symbol"])

        return redirect("/")

    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # user id
    idb = session["user_id"]

    id = int(idb[0]["id"])

    # if does not show anything in the history return apology
    if not db.execute("SELECT * FROM history WHERE user_id= ?", id):
        return apology("Looks empty over here.")
    else:
        historys = db.execute("SELECT * FROM history WHERE user_id= ?", id)
        username = db.execute("SELECT username FROM users WHERE id= ? ", id)
        return render_template("history.html", historys=historys, username=username)




@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # if he submit with the button
    if request.method == "POST":

        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Enter a stock symbol", 400)

        elif not lookup(symbol):
            return apology("Symbol does not exist", 400)

        # ask the API for the information about that symbol
        lookupsymbol = lookup(symbol)

        return render_template("quoted.html", lookupsymbol=lookupsymbol)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # if the user submit a form via POST.
    if request.method == "POST":

        # all usernames must be in lowercase.
        username = request.form.get("username").lower()
        result = db.execute(" SELECT * FROM users WHERE username = ?", username)

        # if the username is not submitted
        if not username:
            return apology("must provide username", 400)

        # if the username is already in the database.
        elif result:
            return apology("username already exists", 400)

        # if the password is not submitted.
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # if the passwords does not match.
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords does not match", 400)

        # generate password hash (databases should never store plain text passwords).
        password = generate_password_hash(request.form.get("password"))

        # insert a row with the posted information by the user.
        db.execute(" INSERT INTO users (username, hash, cash) VALUES (?, ?, 10000.00); ", username, password)

        # log user in.
        login = db.execute (" SELECT id FROM users WHERE username = ?", username)
        session["user_id"] = login[0]["id"]

        # redirect to the homepage.
        return redirect("/")

    # if the user submit a form via GET, link or redirect.
    else:
        return render_template("register.html")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # user id
    idb = session["user_id"]

    id = int(idb[0]["id"])

    stocks = db.execute("SELECT * FROM stocks WHERE user_id= ?", id)
    if request.method == "POST":
        cashdb = db.execute("SELECT cash FROM users WHERE id= ?", id)
        # integer cash rounded to two decimals
        cash = round(cashdb[0]["cash"], 2)
        #iterate over each row of stock and verify which one is trying to sell to update databases
        for stock in stocks:
            if request.form.get("symbol") == stock["stock_symbol"]:
                live_stock = lookup(stock["stock_symbol"])
                shares = int(stock["shares"])
                if int(request.form.get("shares")) <= shares and int(request.form.get("shares")) >= 0:
                    new_cash = cash + (live_stock["price"] * int(request.form.get("shares")))
                    new_shares = shares - int(request.form.get("shares"))
                    db.execute("UPDATE users SET cash= ? WHERE id= ?", new_cash, id)
                    # if shares are the same as the shares available simply delete the row, otherwise update prices
                    if shares == int(request.form.get("shares")):
                        db.execute("DELETE FROM stocks WHERE stock_symbol= ? AND user_id= ?", stock["stock_symbol"], id)
                        db.execute("DELETE FROM stocks_index WHERE stock_symbol= ? AND user_id= ?", stock["stock_symbol"], id)
                    else:
                        db.execute("UPDATE stocks SET shares= ? WHERE stock_symbol= ? AND user_id= ?", new_shares, stock["stock_symbol"], id)
                        db.execute("UPDATE stocks_index SET shares= ? WHERE stock_symbol= ? AND user_id= ?", new_shares, stock["stock_symbol"], id)
                    # insert data to history
                    db.execute("INSERT INTO history (user_id, transaction_type, stock, shares, share_price, total_cost, date) VALUES (?, ?, ?, ?, ?, ?, ?)", id, "sell", stock["stock_symbol"], shares, live_stock["price"], live_stock["price"] * int(request.form.get("shares")), date)
                    return redirect("/")

                return apology("Enter a valid shares number")

        return apology("Enter a valid stock")

    else:
        return render_template("sell.html", stocks=stocks)
