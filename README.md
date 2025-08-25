# Project Overview

The Maritime Assistant is an AI-powered virtual assistant built for the shipping and maritime industry. It combines voice and text interaction to help users with tasks such as accessing weather updates, calculating port distances, summarizing charter party documents, and assisting in laytime calculations. The project integrates a professional user interface with both chat and voice modes, making it a versatile tool for maritime professionals to streamline operations and decision-making.

This repository contains a full-stack application with separate backend and frontend components. Below is a brief description of the structure and setup instructions.

## Directory Structure

```
.
├── backend/        # Python (Flask or similar) backend API & server code
│   ├── api_helpers.py
│   ├── app.py
│   ├── normalize_ports.py
│   ├── normalized_ports.csv
│   ├── ports.csv
│   ├── server.js
│   ├── requirements.txt
│   ├── uploads/
│   ├── node_modules/
│   └── venv/
├── frontend/       # React (Vite) frontend app
│   ├── src/
│   ├── dist/
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── node_modules/
├── package-lock.json
└── venv/
```

## Backend

- **Python API:** Found under `backend/`, implemented in `app.py`, with helpers in `api_helpers.py`.
- **CSV Data:** Multiple CSV files for data processing.
- **Uploads:** Place to store uploaded PDFs.
- **Node.js Server:** May include Express server (`server.js`) for some APIs or static serving.
- **Virtual Environment:** Python venv for dependency isolation.
- **Dependencies:** Listed in `requirements.txt` (Python) and `package.json` (Node.js, if used).

### Backend Setup

1. **Python Setup**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Node.js Setup** (if server.js or npm packages are required)
   ```bash
   npm install
   ```
3. **Run the Python API**
   ```bash
   python app.py
   ```
4. **Run the Node.js Server** (if needed)
   ```bash
   node server.js
   ```

## Frontend

- **React App (Vite):** Source code in `frontend/src/`, entry point is `main.jsx`.
- **Styling:** Uses Tailwind CSS and PostCSS.
- **Build Output:** Production files in `frontend/dist/`.

### Frontend Setup

1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```
2. **Run development server**
   ```bash
   npm run dev
   ```
3. **Build for production**
   ```bash
   npm run build
   ```

## Common Tasks

- **Start Backend**: See backend setup above.
- **Start Frontend**: See frontend setup above.
- **CSV Data**: Place or update CSV files in the backend directory as needed.
- **Uploads**: Upload files (e.g., PDFs) to `backend/uploads/`.

## Notes

- Make sure to activate the correct Python virtual environment before running backend scripts.
- Ensure Node.js and npm are installed for frontend and any backend Node.js server tasks.
- CSV files are used for port data normalization and processing.
- The app may have both Python and Node.js backend components; use as needed.

## License

This project is licensed under the MIT License.

---

Feel free to update this README with additional details about usage, configuration, or deployment as your project evolves.
