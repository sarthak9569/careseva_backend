const mongoose = require('mongoose');

const hospitalSchema = new mongoose.Schema({
  name: { type: String, required: true },
  code: { type: String, required: true, unique: true },
  adminId: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  address: { type: String, required: true },
  city: { type: String, required: true },
  state: { type: String, required: true },
  pincode: { type: String, required: true },
  contact: { type: String },
  email: { type: String, required: true },
  website: { type: String },
  registrationNumber: { type: String },
  status: { type: String, enum: ['Active', 'Inactive'], default: 'Active' },
  type: { 
    type: String, 
    enum: ['Government', 'Private', 'Trust'], 
    default: 'Private' 
  },
  settings: {
    maxDailyPatients: { type: Number, default: 1000 },
    allowOnlineBooking: { type: Boolean, default: true },
    workingHours: {
      open: { type: String, default: '09:00' },
      close: { type: String, default: '18:00' }
    }
  }
}, { timestamps: true });

// Indexing for fast search
hospitalSchema.index({ name: 'text', city: 1, pincode: 1 });
// For department filtering, we can query departments but often it's faster to have a search array or use aggregation.
// We'll stick to a clean schema and use proper aggregation or subqueries.

module.exports = mongoose.model('Hospital', hospitalSchema);
