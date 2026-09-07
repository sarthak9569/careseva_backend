const mongoose = require('mongoose');

const medicalRecordSchema = new mongoose.Schema({
  patient: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  diagnosis: String,
  history: String,
  treatment: String,
  prescriptions: [String],
  dischargeSummary: String,
  records: [{
    type: { type: String, enum: ['Report', 'scan', 'Prescription'] },
    url: String,
    date: { type: Date, default: Date.now }
  }]
}, { timestamps: true });

module.exports = mongoose.model('MedicalRecord', medicalRecordSchema);
