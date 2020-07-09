from androguard.core.bytecodes import dvm

from androguard.core.analysis import analysis


class Stack:
    def __init__(self):
        self.__elems = []

    def __len__(self):
        return len(self.__elems)

    def gets(self):
        return self.__elems

    def get_op_code_by_idx(self, idx):
        return self.__elems[idx][0]

    def get_op_value_by_idx(self, idx):
        return self.__elems[idx][1]

    def push(self, elem):
        self.__elems.append(elem)

    def get(self):
        return self.__elems[-1]

    def pop(self):
        return self.__elems.pop(-1)

    def nil(self):
        return len(self.__elems) == 0

    def insert_stack(self, idx, elems):
        if elems != self.__elems:
            for i in elems:
                self.__elems.insert(idx, i)
                idx += 1

    def show(self):
        nb = 0

        if len(self.__elems) == 0:
            print("\t--> nil")

        for i in self.__elems:
            print("\t-->", nb, ": ", i)
            nb += 1


class RegisterAnalyzerVMResult(object):
    def __init__(self, path, result):
        self.__path = path
        self.__result = result

    def getPath(self):
        return self.__path

    def getResult(self):
        return self.__result

    def is_string(self, param):
        try:
            if isinstance(self.__result[param], str):
                return True

            return False
        except TypeError:
            return False
        except KeyError:
            return False

    def is_class_container(self, param):
        try:
            return isinstance(self.__result[param], RegisterAnalyzerVMClassContainer)
        except TypeError:
            return False
        except NameError:
            return False
        except KeyError:
            return False


# Added by AndroBugs
class RegisterAnalyzerVMClassContainer(object):

    def __init__(self, class_name, class_idx):
        self._register = {}
        self.__ins_stack = Stack()

        self.__class_name = class_name
        self.__class_idx = class_idx

        self.__invoked_method_list = []  # Only save "invoke-virtual"

    def add_invoke_method(self, method_name_string):
        self.__invoked_method_list.append(method_name_string)

    def get_invoked_method_list(self):
        return self.__invoked_method_list

    def get_class_name(self):
        return self.__class_name

    def get_class_idx(self):
        return self.__class_idx

    def add_an_instruction(self, ins):
        pass


class RegisterAnalyzerVMImmediateValue(object):
    # Static DVM Engine (StaticDVM_Engine, StaticDVMEngine, Static_DVM_Engine)

    def __init__(self, ins=None, max_trace=-1, trace_extra_offset_ins=0):
        self._register = {}
        self.__ins_stack = Stack()

        if ins is not None:
            self.load_instructions(ins, max_trace, trace_extra_offset_ins)  # Initialize With load registers

    """
        See reference: http://source.android.com/devices/tech/dalvik/dalvik-bytecode.html
        Consider this situation:
        --> 0 :  [(0, 3), (1, 0)]  => const/4 v3, 0
        --> 1 :  [(0, 2), (1, 2)]
        --> 2 :  [(0, 4), (256, 5061, 'Lcom/example/androidurlaccesstesting1/MainActivity;->getApplicationContext()Landroid/content/Context;')]
        --> 3 :  [(0, 0)]
        --> 4 :  [(0, 1), (257, 5823, "'test.db'")]  => const-string v1, 'test.db'
    """

    def __add(self, ins, reg_list):
        if reg_list is not None:
            self.__ins_stack.push(
                [ins, reg_list])  # Only register number and value, no instruction. Format: [ins, [(0, 3), (1, 0)]]

            if 0x12 <= ins <= 0x1c:  # [const] or [const/xx] or [const-string]
                dst_register_pair = reg_list[0]
                src_register_pair = reg_list[1]
                if dst_register_pair[0] == dvm.OPERAND_REGISTER:
                    dst_register_number = dst_register_pair[1]

                    if src_register_pair[0] & dvm.OPERAND_KIND:  # has three  dvm.OPERAND_KIND=0x100
                        src_operand = src_register_pair[0] & (
                            ~dvm.OPERAND_KIND)  # Clear "OPERAND_KIND" bit, equal to src_operand = src_register_pair[0]- 0x100
                        immediate_value = src_register_pair[2]
                        self._register[dst_register_number] = self.strip_string(immediate_value)
                        # print("### register[" + str(dst_register_number) + "] = " + str(src_register_pair[2]) + " ###")
                    else:
                        if src_register_pair[0] == dvm.OPERAND_LITERAL:  # should always be "dvm.OPERAND_LITERAL"
                            immediate_value = src_register_pair[1]
                            self._register[dst_register_number] = self.strip_string(immediate_value)
                            # print("### register[" + str(dst_register_number) + "] = " + str(src_register_pair[1]) + " ###")

            elif 0x0a <= ins <= 0x0d:  # [move-result vAA] or [move-result-wide vAA] or [move-result-object vAA] or [move-exception vAA]
                # reg_list[0][0] would always be "dvm.OPERAND_REGISTER", so we don't need to check
                register_number = reg_list[0][1]
                self._register[register_number] = None

            elif (0x44 <= ins <= 0x4A) or (0x52 <= ins <= 0x58) or (
                    0x60 <= ins <= 0x66):  # [aget] or [aget-xxxx] or [iget] or [iget-xxxx] or [sget] or [sget-xxxx]
                # reg_list[0][0] would always be "dvm.OPERAND_REGISTER", so we don't need to check
                register_number = reg_list[0][1]
                self._register[register_number] = None

            elif ins == 0x22:  # [new-instance vA, Lclass/name;]
                # reg_list[0][0] would always be "dvm.OPERAND_REGISTER", so we don't need to check
                register_number = reg_list[0][1]
                new_instance_class_idx = reg_list[1][1]
                new_instance_class_name = reg_list[1][2]
                self._register[register_number] = RegisterAnalyzerVMClassContainer(new_instance_class_name,
                                                                                   new_instance_class_idx)
                # print("### New instance => register number: " + str(self._register[register_number]) + " ###")

            elif ins == 0x6e:  # [invoke-virtual]
                register_number = reg_list[0][1]
                operands = reg_list[-1]
                if (operands[0] == dvm.OPERAND_KIND) and (register_number in self._register):
                    clz_invoked = self._register[register_number]
                    if self.is_class_container(clz_invoked):
                        clz_invoked.add_invoke_method(operands[-1])

    def load_instructions(self, ins, max_trace=-1, trace_extra_offset_ins=0):
        if max_trace == -1:  # Load all instructions
            for i in ins:  # method.get_instructions(): Instruction
                self.__add(i.get_op_value(), i.get_operands())
                # print "\t", i.get_name(), i.get_output(), ", kind: ", hex(i.get_op_value())
        else:
            idx = 0
            for i in ins:  # method.get_instructions(): Instruction
                self.__add(i.get_op_value(), i.get_operands())
                idx += i.get_length()
                if idx > max_trace:
                    if trace_extra_offset_ins <= 0:  # No extra instructions need to trace
                        break
                    else:
                        trace_extra_offset_ins = trace_extra_offset_ins - 1
                # print "\t", "%x" % idx, i.get_name(), i.get_output(), ", kind: ", hex(i.get_op_value())

    def strip_string(self, value):
        """
            When checking if an object is a string, keep in mind that it might be a unicode string too!
            In Python 2, str and unicode have a common base class, basestring, so you can do: if isinstance(value, basestring)
            Note that in Python 3, unicode and basestring no longer exist (there is only str) and
            a bytes object is no longer a kind of string (it is a sequence of integers instead)
        """
        if isinstance(value, str):
            return value[1:-1]  # strip the left and right '
        return value

    def has_if_or_switch_instructions(self):
        try:
            for ins in self.__ins_stack.gets():
                if (0x32 <= ins[0] <= 0x3D) or (0x2B <= ins[0] <= 0x2C):  # if or switch
                    return True
            return False
        except:
            return None

    def get_ins_return_boolean_value(self):
        try:
            if len(self.__ins_stack) == 2:
                full_ins_first = self.__ins_stack.gets()[-2]
                full_ins_last = self.__ins_stack.gets()[-1]

                # 0x12 => const/4 vx,lit4
                # 0x0F => return vx
                if (full_ins_first[0] == 0x12) and (full_ins_last[0] == 0x0F):  # check the instruction
                    ins_first_register_number_value = full_ins_first[1]

                    if ins_first_register_number_value[1][1] == 1:
                        return True
                    else:
                        return False

        except IndexError:
            return None

    def is_class_container(self, value):  # value is the parameter index
        if not value:
            return False
        return isinstance(value, RegisterAnalyzerVMClassContainer)

    def show(self):
        self.__ins_stack.show()

    def get_stack(self):
        return self.__ins_stack

    def get_register_table(self):
        return self._register

    def get_register_number_to_register_value_mapping(self):
        if (self._register is None) or (self.__ins_stack is None):
            return None

        l = []
        try:
            last_ins = self.__ins_stack.get()[1]
            for ins in last_ins:
                if ins[0] == dvm.OPERAND_REGISTER:
                    l.append(self.get_register_value(ins[1]))  # ins[1] is the register number
                else:
                    l.append(None)

            return l
        except IndexError:
            return None

    def get_register_value_by_param_in_last_ins(self, param):

        if (self._register is None) or (self.__ins_stack is None):
            return None

        """
            Example code:
            invoke-virtual v2, v3, v6, v4, v5, Landroid/content/Context;->openOrCreateDatabase(Ljava/lang/String; I Landroid/database/sqlite/SQLiteDatabase$CursorFactory; Landroid/database/DatabaseErrorHandler;)Landroid/database/sqlite/SQLiteDatabase;
            [(0, 2), (0, 3), (0, 6), (0, 4), (0, 5), (256, 147, 'Landroid/content/Context;->openOrCreateDatabase(Ljava/lang/String; I Landroid/database/sqlite/SQLiteDatabase$CursorFactory; Landroid/database/DatabaseErrorHandler;)Landroid/database/sqlite/SQLiteDatabase;')]
        """

        try:
            last_ins = self.__ins_stack.get()
            last_ins_register_pair = last_ins[param]
            if last_ins_register_pair is not None:
                return self.get_register_value(last_ins_register_pair[1])
            return None
        except IndexError:
            return None

    def get_register_value(self, register):
        try:
            if register in self._register:
                return self._register[register]
            else:
                return None
        except KeyError:
            return None


def get_source_path(vm, path):
    cm = vm.get_class_manager()

    src_class_name, src_method_name, src_descriptor = path.get_src(cm)
    dst_class_name, dst_method_name, dst_descriptor = path.get_dst(cm)

    x = {
        "src_class_name": src_class_name,
        "src_method_name": src_method_name,
        "src_descriptor": src_descriptor,
        "idx": path.get_idx(),
        "dst_class_name": dst_class_name,
        "dst_method_name": dst_method_name,
        "dst_descriptor": dst_descriptor,
        "path": path
    }

    return x


def get_source_paths(vm, paths):
    """
        Show paths of packages
        :param paths: a list of :class:`PathP` objects
    """
    l = []
    for path in paths:
        l.append(get_source_path(vm, path))

    return l


def trace_register_value_by_param_in_source_paths(vm: dvm, analysis: analysis, paths):
    paths = get_source_paths(vm, paths)  # transform 'PathP' to name and descriptor of 'src' and 'dst' dictionary

    if paths is None:
        return []

    results = []

    for path in paths:

        src_class_name = path["src_class_name"]
        src_method_name = path["src_method_name"]
        src_descriptor = path["src_descriptor"]
        max_trace = path["idx"]
        path = path["path"]

        if (src_class_name is None) or (src_method_name is None) or (src_descriptor is None) or (max_trace is None):
            continue

        # Get all instructions for the specific method inside the current Path
        # method = vm.get_specific_class_method_descriptor(src_class_name, src_method_name, src_descriptor)
        # TODO might be a better solution
        method = list(analysis.find_methods(src_class_name, src_method_name, src_descriptor))[0].get_method()

        if method is None:  # do not find method
            continue

        register_analyzer = RegisterAnalyzerVMImmediateValue()
        register_analyzer.load_instructions(method.get_instructions(), max_trace)
        result = RegisterAnalyzerVMResult(path, register_analyzer.get_register_number_to_register_value_mapping())
        results.append(result)

    return results
