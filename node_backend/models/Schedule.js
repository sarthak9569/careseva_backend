const mongoose = require('mongoose');

const scheduleSchema = new mongoose.Schema({
  doctor: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor', required: true },
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  workingDays: [{ type: String }], // ['Monday', 'Wednesday']
  shifts: [{
    startTime: { type: String }, // e.g. "09:00"
    endTime: { type: String },   // e.g. "13:00"
    shiftType: { type: String, enum: ['Morning', 'Evening', 'Night', 'Full-Day'] }
  }],
  department: { type: mongoose.Schema.Types.ObjectId, ref: 'Department' }
}, { timestamps: true });

module.exports = mongoose.model('Schedule', scheduleSchema);
