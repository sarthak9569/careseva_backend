const mongoose = require('mongoose');

const queueSchema = new mongoose.Schema({
  queue_number: { type: Number, required: true },
  patient_name: { type: String, required: true },
  phone: { type: String, default: null },
  department: { type: mongoose.Schema.Types.ObjectId, ref: 'Department', required: true },
  doctor: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor', default: null },
  status: { type: String, enum: ['waiting', 'current', 'completed', 'cancelled'], default: 'waiting' },
  is_skipped: { type: Boolean, default: false },
  source: { type: String, enum: ['web', 'ivr', 'mobile', 'qr'], default: 'web' },
  called_at: { type: Date, default: null },
  completed_at: { type: Date, default: null },
}, { timestamps: true });

module.exports = mongoose.model('Queue', queueSchema);