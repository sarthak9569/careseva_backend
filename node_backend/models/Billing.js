const mongoose = require('mongoose');

const billingSchema = new mongoose.Schema({
  hospital: { type: mongoose.Schema.Types.ObjectId, ref: 'Hospital', required: true },
  patient: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  items: [{
    description: String,
    amount: Number,
    quantity: { type: Number, default: 1 }
  }],
  totalAmount: Number,
  insuranceStatus: { type: String, enum: ['None', 'Pending', 'Claimed', 'Rejected'], default: 'None' },
  status: { type: String, enum: ['Unpaid', 'Paid', 'Partial'], default: 'Unpaid' },
  receiptNumber: String
}, { timestamps: true });

module.exports = mongoose.model('Billing', billingSchema);
