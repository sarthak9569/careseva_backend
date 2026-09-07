const mongoose = require('mongoose');

const staffSchema = new mongoose.Schema({
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  staffId: { type: String, required: true }, // Not globally unique, but should be unique per hospital (logic in controller)
  name: { type: String, required: true },
  role: { 
    type: String, 
    enum: ['Receptionist', 'Nurse', 'Lab Technician', 'Pharmacist', 'Administrator'], 
    required: true 
  },
  contactDetails: { type: String },
  department: { type: mongoose.Schema.Types.ObjectId, ref: 'Department' },
  joiningDate: { type: Date, default: Date.now },
  status: { type: String, enum: ['Active', 'Inactive'], default: 'Active' }
}, { timestamps: true });

module.exports = mongoose.model('Staff', staffSchema);
