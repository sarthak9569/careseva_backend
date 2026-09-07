const mongoose = require('mongoose');

const leaveSchema = new mongoose.Schema({
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  applicant: { 
    type: mongoose.Schema.Types.ObjectId, 
    refPath: 'applicantModel', 
    required: true 
  },
  applicantModel: {
    type: String,
    required: true,
    enum: ['Doctor', 'Staff']
  },
  startDate: { type: Date, required: true },
  endDate: { type: Date, required: true },
  reason: { type: String, required: true },
  substitute: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor' }, // The doctor taking charge
  status: { 
    type: String, 
    enum: ['Pending', 'Approved', 'Rejected'], 
    default: 'Pending' 
  },
  approvalDate: { type: Date },
  approvedBy: { type: mongoose.Schema.Types.ObjectId, ref: 'User' }
}, { timestamps: true });

module.exports = mongoose.model('Leave', leaveSchema);
