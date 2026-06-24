# CIO Manager

**Communicate with your CIO members, take attendance automatically, and more!**

CIO Manager is a web platform built for student organizations (CIOs) at UVA to streamline communication, automate attendance tracking, and manage membership — all in one place.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributors

Built by Team A-20 for CS 3240 at the University of Virginia.

---

## Dependencies

- Python 3.x
- Django
- Uvicorn (ASGI server)
- See `requirements.txt` for the full list

---

## Setup

Standard Django project setup:

```bash
git clone https://github.com/uva-cs3240-s26/project-a-20.git
cd project-a-20
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Database Setup

```bash
python manage.py migrate
```

---

## Running the Server

```bash
.venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --reload
```

Then visit [localhost:8000](http://localhost:8000) to access the app.
