const mongoose = require('mongoose');

const admissionSchema = new mongoose.Schema({
  patient: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  doctor: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor' },
  wardNumber: String,
  bedNumber: String,
  admissionDate: { type: Date, default: Date.now },
  dischargeDate: Date,
  conditionOnDischarge: String,
  referralDetails: String,
  status: { type: String, enum: ['Admitted', 'Discharged', 'Transferred'], default: 'Admitted' }
}, { timestamps: true });

module.exports = mongoose.model('Admission', admissionSchema);
