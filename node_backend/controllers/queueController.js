const Queue = require('../models/Queue');
const Department = require('../models/Department');
const Doctor = require('../models/Doctor');
const Settings = require('../models/Settings');

async function getNextQueueNumber() {
  const today = new Date().toISOString().split('T')[0];
  let settings = await Settings.findOne();
  if (!settings) {
    settings = await Settings.create({ queue_counter: 0, queue_date: today });
  }
  if (settings.queue_date !== today) {
    settings.queue_counter = 0;
    settings.queue_date = today;
  }
  settings.queue_counter += 1;
  await settings.save();
  return settings.queue_counter;
}

async function getEstimatedWait(departmentId, position) {
  const dept = await Department.findById(departmentId);
  return position * (dept ? dept.avg_consultation_time : 10);
}

// POST /api/queue/join
const joinQueue = async (req, res) => {
  try {
    const { patient_name, phone, department_id, source = 'web' } = req.body;
    if (!patient_name || !department_id)
      return res.status(400).json({ error: 'Name and department are required' });

    const dept = await Department.findById(department_id);
    if (!dept) return res.status(404).json({ error: 'Department not found' });

    const queue_number = await getNextQueueNumber();

    const doctor = await Doctor.findOne({ department: department_id, status: 'available' });

    const entry = await Queue.create({
      queue_number,
      patient_name,
      phone: phone || null,
      department: department_id,
      doctor: doctor?._id || null,
      source,
    });

    const position = await Queue.countDocuments({
      department: department_id,
      status: 'waiting',
      _id: { $lte: entry._id }
    });

    const estimated_wait = await getEstimatedWait(department_id, position);

    // Socket.io — notify everyone in this department
    const io = req.app.get('io');
    io.to(`dept_${department_id}`).emit('queue_updated', { department_id });
    io.emit('stats_updated');

    res.status(201).json({
      success: true,
      queue_number,
      patient_name,
      position,
      estimated_wait,
      department_name: dept.name,
      entry_id: entry._id,
      message: `You are #${queue_number}. Estimated wait: ${estimated_wait} minutes`,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
};

// GET /api/queue
const getQueue = async (req, res) => {
  try {
    const { department_id } = req.query;
    const filter = { status: { $in: ['waiting', 'current'] } };
    if (department_id) filter.department = department_id;

    const queue = await Queue.find(filter)
      .populate('department', 'name avg_consultation_time')
      .populate('doctor', 'name')
      .sort({ queue_number: 1 });

    const enriched = await Promise.all(queue.map(async (q, i) => {
      const wait = await getEstimatedWait(q.department._id, i);
      return {
        ...q.toObject(),
        position: i + 1,
        estimated_wait: wait,
        department_name: q.department?.name,
        doctor_name: q.doctor?.name,
      };
    }));

    res.json({ success: true, queue: enriched });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// GET /api/queue/status
const getPatientStatus = async (req, res) => {
  try {
    const { queue_number, department_id } = req.query;

    const patient = await Queue.findOne({
      queue_number: parseInt(queue_number),
      department: department_id,
    }).populate('department', 'name avg_consultation_time');

    if (!patient) return res.status(404).json({ error: 'Not found' });

    const ahead = await Queue.countDocuments({
      department: department_id,
      status: 'waiting',
      queue_number: { $lt: parseInt(queue_number) },
    });

    const position = ahead + 1;
    const estimated_wait = await getEstimatedWait(department_id, position);

    res.json({
      success: true,
      patient: {
        ...patient.toObject(),
        department_name: patient.department?.name,
      },
      position,
      estimated_wait,
    });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// GET /api/queue/stats
const getStats = async (req, res) => {
  try {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const [waiting, current, completed, byDept] = await Promise.all([
      Queue.countDocuments({ status: 'waiting' }),
      Queue.countDocuments({ status: 'current' }),
      Queue.countDocuments({ status: 'completed', createdAt: { $gte: today } }),
      Queue.aggregate([
        { $match: { status: { $in: ['waiting', 'current'] } } },
        { $group: { _id: '$department', count: { $sum: 1 } } },
        { $lookup: { from: 'departments', localField: '_id', foreignField: '_id', as: 'dept' } },
        { $unwind: '$dept' },
        { $project: { name: '$dept.name', count: 1 } },
      ]),
    ]);

    res.json({
      success: true,
      stats: {
        waiting,
        current,
        completed_today: completed,
        by_department: byDept,
      },
    });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// PUT /api/queue/complete/:id
const completePatient = async (req, res) => {
  try {
    const patient = await Queue.findById(req.params.id);
    if (!patient) return res.status(404).json({ error: 'Not found' });

    patient.status = 'completed';
    patient.completed_at = new Date();
    await patient.save();

    const next = await Queue.findOne({
      department: patient.department,
      status: 'waiting',
    }).sort({ queue_number: 1 });

    if (next) {
      next.status = 'current';
      next.called_at = new Date();
      await next.save();
    }

    const io = req.app.get('io');
    io.to(`dept_${patient.department}`).emit('queue_updated', {
      department_id: patient.department,
      next_patient: next,
    });
    io.emit('stats_updated');

    res.json({ success: true, next_patient: next });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// POST /api/queue/next
const callNext = async (req, res) => {
  try {
    const { department_id } = req.body;

    await Queue.updateMany(
      { department: department_id, status: 'current' },
      { status: 'completed', completed_at: new Date() }
    );

    const next = await Queue.findOne({
      department: department_id,
      status: 'waiting',
    }).sort({ queue_number: 1 });

    if (next) {
      next.status = 'current';
      next.called_at = new Date();
      await next.save();
    }

    const io = req.app.get('io');
    io.to(`dept_${department_id}`).emit('queue_updated', { department_id, next_patient: next });
    io.emit('stats_updated');

    res.json({ success: true, current_patient: next });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// POST /api/queue/reset
const resetQueue = async (req, res) => {
  try {
    await Queue.updateMany(
      { status: { $in: ['waiting', 'current'] } },
      { status: 'completed', completed_at: new Date() }
    );
    await Settings.updateOne({}, { queue_counter: 0 });

    const io = req.app.get('io');
    io.emit('queue_updated', { reset: true });
    io.emit('stats_updated');

    res.json({ success: true, message: 'Queue reset successfully' });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// POST /api/queue/skip/:id
const skipPatient = async (req, res) => {
  try {
    const patient = await Queue.findById(req.params.id);
    if (!patient) return res.status(404).json({ error: 'Not found' });

    patient.status = 'waiting';
    patient.is_skipped = true;
    // Push them to the end of the line by updating their creation date slightly or just letting them be re-called
    patient.createdAt = new Date(); 
    await patient.save();

    const next = await Queue.findOne({
      department: patient.department,
      status: 'waiting',
      _id: { $ne: patient._id }
    }).sort({ queue_number: 1 });

    if (next) {
      next.status = 'current';
      next.called_at = new Date();
      await next.save();
    }

    const io = req.app.get('io');
    io.to(`dept_${patient.department}`).emit('queue_updated', { department_id: patient.department });
    io.emit('stats_updated');

    res.json({ success: true, next_patient: next });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// POST /api/queue/pause/:id
const togglePause = async (req, res) => {
  try {
    const dept = await Department.findById(req.params.id);
    if (!dept) return res.status(404).json({ error: 'Department not found' });

    dept.status = dept.status === 'active' ? 'paused' : 'active';
    await dept.status === 'paused';
    await dept.save();

    const io = req.app.get('io');
    io.emit('queue_updated', { department_id: dept._id, paused: dept.status === 'paused' });

    res.json({ success: true, status: dept.status });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

// POST /api/queue/transfer/:id
const transferPatient = async (req, res) => {
  try {
    const { new_department_id } = req.body;
    const patient = await Queue.findById(req.params.id);
    if (!patient) return res.status(404).json({ error: 'Not found' });

    const oldDept = patient.department;
    patient.department = new_department_id;
    patient.status = 'waiting';
    await patient.save();

    const io = req.app.get('io');
    io.to(`dept_${oldDept}`).emit('queue_updated', { department_id: oldDept });
    io.to(`dept_${new_department_id}`).emit('queue_updated', { department_id: new_department_id });
    io.emit('stats_updated');

    res.json({ success: true, patient });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
};

module.exports = {
  joinQueue, getQueue, getPatientStatus,
  getStats, completePatient, callNext, resetQueue,
  skipPatient, togglePause, transferPatient
};