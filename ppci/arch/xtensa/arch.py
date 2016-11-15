
import io
from ...binutils.assembler import BaseAssembler
from ..arch import Architecture, Label, Alignment
from ..data_instructions import Db, Dd, Dcd2, data_isa
from .registers import register_classes
from . import registers
from . import instructions
from ... import ir


class XtensaArch(Architecture):
    name = 'xtensa'

    def __init__(self, options=None):
        super().__init__(options=options, register_classes=register_classes)
        self.isa = instructions.core_isa + data_isa
        self.assembler = BaseAssembler()
        self.assembler.gen_asm_parser(self.isa)
        self.fp = registers.a7  # TODO: does this make sense?

        # TODO: figure out what is the right abi:
        self.callee_save = (registers.a5, registers.a6)

    def move(self, dst, src):
        """ Generate a move from src to dst """
        return instructions.Mov(dst, src)

    def get_runtime(self):
        from ...api import c3c
        obj = c3c([io.StringIO(RT_C3_SRC)], [], self)
        return obj

    def determine_arg_locations(self, arg_types):
        arg_locs = []
        live_in = set([self.fp])
        int_regs = [
            registers.a2, registers.a3, registers.a4, registers.a5,
            registers.a6]
        for arg_type in arg_types:
            # Determine register:
            if arg_type in [ir.i8, ir.u8, ir.i32, ir.u32, ir.ptr]:
                reg = int_regs.pop(0)
            else:  # pragma: no cover
                raise NotImplementedError(str(arg_type))
            arg_locs.append(reg)
            live_in.add(reg)
        return arg_locs, tuple(live_in)

    def determine_rv_location(self, ret_type):
        """ return value in a2 """
        # TODO: what is the frame pointer??
        live_out = set([self.fp])
        if ret_type in [ir.i8, ir.u8, ir.i32, ir.u32, ir.ptr]:
            rv = registers.a2
        else:  # pragma: no cover
            raise NotImplementedError(str(ret_type))
        live_out.add(rv)
        return rv, tuple(live_out)

    def gen_fill_arguments(self, arg_types, args, live):
        """ This function moves arguments in the proper locations. """
        arg_locs, live_in = self.determine_arg_locations(arg_types)
        live.update(set(live_in))

        # Setup parameters:
        for arg_loc, arg in zip(arg_locs, args):
            if isinstance(arg_loc, registers.AddressRegister):
                yield self.move(arg_loc, arg)
            else:  # pragma: no cover
                raise NotImplementedError('Parameters in memory not impl')

    def make_call(self, frame, vcall):
        live_regs = frame.live_regs_over(vcall)

        # Caller save registers:
        for register in live_regs:
            # yield self.push(register)
            pass

        yield instructions.Call0(vcall.function_name)

        # Restore caller save registers:
        for register in reversed(live_regs):
            # yield self.pop(register)
            pass

    def gen_prologue(self, frame):
        """ Returns prologue instruction sequence """
        # Literal pool must reside before function!
        for label, value in frame.constants:
            yield Alignment(4)
            yield Label(label)
            if isinstance(value, bytes):
                for byte in value:
                    yield Db(byte)
            elif isinstance(value, int):
                yield Dd(value)
            elif isinstance(value, str):
                yield Dcd2(value)
            else:  # pragma: no cover
                raise NotImplementedError('Constant {}'.format(value))

        # Label indication function:
        yield Label(frame.name)

        # Callee save registers:
        for reg in self.callee_save:
            if frame.is_used(reg):
                pass
                # yield self.push(reg)

        # Reserve stack space
        if frame.stacksize > 0:
            self.logger.warning('Figure out how to create stack')
            # TODO: calculate 2 complement properly:
            size = 256 - frame.stacksize
            yield instructions.Addi(registers.a1, registers.a1, size)

    def gen_epilogue(self, frame):
        """ Return epilogue sequence """
        if frame.stacksize > 0:
            size = frame.stacksize
            yield instructions.Addi(registers.a1, registers.a1, size)

        # Pop save registers back:
        for reg in reversed(self.callee_save):
            if frame.is_used(reg):
                # yield self.pop(reg)
                pass

        # yield self.pop(self.fp)
        yield instructions.Ret()


# TODO: find a common place for this:
RT_C3_SRC = """
    module swmuldiv;
    function int div(int num, int den)
    {
      var int res = 0;
      var int current = 1;

      while (den < num)
      {
        den = den << 1;
        current = current << 1;
      }

      while (current != 0)
      {
        if (num >= den)
        {
          num -= den;
          res = res | current;
        }
        den = den >> 1;
        current = current >> 1;
      }
      return res;
    }

    function int mul(int a, int b)
    {
      var int res = 0;
      while (b > 0)
      {
        if ((b & 1) == 1)
        {
          res += a;
        }
        a = a << 1;
        b = b >> 1;
      }
      return res;
    }
"""
