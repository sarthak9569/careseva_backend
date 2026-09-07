const mongoose = require('mongoose');

const departmentSchema = new mongoose.Schema({
  name: { type: String, required: true },
  code: { type: String, required: true },
  description: { type: String },
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  status: { type: String, enum: ['Active', 'Inactive'], default: 'Active' },
}, { timestamps: true });

// Ensure names are unique ONLY within the same hospital, not across the whole app
departmentSchema.index({ hospital: 1, name: 1 }, { unique: true });

module.exports = mongoose.model('Department', departmentSchema);
