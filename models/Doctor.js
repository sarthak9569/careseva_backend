const mongoose = require('mongoose');

const doctorSchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  name: { type: String, required: true },
  docId: { type: String, required: true }, // Unique clinical identifier within a hospital
  qualification: { type: String },
  specialization: { type: String },
  medicalRegistrationNumber: { type: String },
  contactNumber: { type: String },
  email: { type: String },
  department: { type: mongoose.Schema.Types.ObjectId, ref: 'Department', required: true },
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital' },
  joiningDate: { type: Date, default: Date.now },
  status: { type: String, enum: ['active', 'inactive'], default: 'active' },
  employmentStatus: { type: String, enum: ['Permanent', 'Contract', 'Visiting'], default: 'Permanent' },
}, { timestamps: true });

module.exports = mongoose.model('Doctor', doctorSchema);