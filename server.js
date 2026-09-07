require('dotenv').config();
const express = require('express');
const http = require('http');
const mongoose = require('mongoose');
const { Server } = require('socket.io');
const cors = require('cors');
const connectDB = require('./config/db');

// Prevent unhandled promise rejections (e.g. mongoose DNS failures) from crashing the process
process.on('unhandledRejection', (reason) => {
  console.warn('Unhandled Rejection (suppressed to keep server alive):', reason?.message || reason);
});

const app = express();
const server = http.createServer(app);


// Socket.io setup
const io = new Server(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] }
});

app.set('io', io);
app.use(cors());
// Twilio webhooks send application/x-www-form-urlencoded by default
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

// Request Logger
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// Routes
app.use('/api/auth', require('./routes/auth'));
app.use('/api/queue', require('./routes/queue'));
app.use('/api/ivr', require('./routes/ivr'));
app.use('/api/prescriptions', require('./routes/prescriptions'));
app.use('/api/admin', require('./routes/admin'));

// Health check
app.get('/api/health', (req, res) => {
  const ok = mongoose.connection.readyState === 1;
  res.json({
    status: ok ? 'ok' : 'degraded',
    db: ok ? `connected (${mongoose.connection.host})` : 'not connected',
  });
});

io.on('connection', (socket) => {
  console.log('User connected to Sanctuary Socket:', socket.id);
  socket.on('disconnect', () => console.log('User disconnected from Sanctuary Socket'));
});

const PORT = process.env.PORT || 5000;

connectDB().then(() => {
  server.listen(PORT, () => {
    console.log(`CareQueue Backend running on port ${PORT}`);
  });
});
