"""
Flask-WTF form classes.

Each POST endpoint in routes.py has a matching FlaskForm subclass here.
Phase C of the security refactor wires them into the routes one at a
time — until then this module is dormant (imports succeed but nothing
references the classes yet).

Why FlaskForm at all (not just raw <form> tags + manual validation):

1. CSRF tokens for free. Flask-WTF embeds a signed CSRF token in every
   FlaskForm via ``{{ form.hidden_tag() }}``, and ``form.validate_on_submit()``
   refuses any POST whose token doesn't match. This is what the security
   lecture flags as the standard CSRF defence.

2. Validation moves out of the route. Length / format / required-field
   checks live next to the field declaration, not interleaved with the
   business logic of the handler.

3. Re-render the form with errors and prior input on validation failure
   without manually re-passing every field through ``request.form.<x> or ''``.

The four forms below cover all four POST routes; routes that only need
a CSRF token (e.g. the delete-itinerary button) get an empty FlaskForm
subclass so the same ``form.hidden_tag()`` + ``form.validate_on_submit()``
pattern applies uniformly.
"""

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Regexp,
    ValidationError,
)


class RegisterForm(FlaskForm):
    """New-account form posted to /register."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Please choose a username."),
            Length(min=3, max=30, message="Username must be between 3 and 30 characters."),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="Username may only contain letters, numbers, and underscores.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Please enter your email."),
            Email(message="A valid email is required."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Please enter a password."),
            Length(min=6, message="Password must be at least 6 characters."),
        ],
    )
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    """Sign-in form posted to /login. Accepts username or email in one field."""

    username = StringField(
        "Username or email",
        validators=[DataRequired(message="Please enter your username or email.")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Please enter your password.")],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")


class NewItineraryForm(FlaskForm):
    """Trip-planner form posted to /itinerary/new from the homepage."""

    destination = StringField(
        "Destination",
        validators=[DataRequired(message="Please enter a destination.")],
    )
    start_date = DateField(
        "Start date",
        validators=[DataRequired(message="Please select a start date.")],
    )
    end_date = DateField(
        "End date",
        validators=[DataRequired(message="Please select an end date.")],
    )
    submit = SubmitField("Plan trip")

    def validate_end_date(self, field):
        """Cross-field check: end must not precede start."""
        if self.start_date.data and field.data and field.data < self.start_date.data:
            raise ValidationError("End date must be on or after the start date.")


class DeleteItineraryForm(FlaskForm):
    """No data fields — exists purely so the dashboard delete buttons get a
    CSRF token via ``{{ delete_form.hidden_tag() }}`` and the route can call
    ``form.validate_on_submit()``."""
